"""An exact, size-limited oracle for one rectangular cutter on a rectangular lawn.

See README.md for the finite-grid and edge-multiplicity arguments. Coordinates
are integer cutter-center positions; lawn cells are identified by lower left
corners. Polygon bounds use the usual exclusive right/top cell coordinates.
"""

from dataclasses import dataclass
from math import isfinite

from cgshop2027_pyutils.schemas import CGSHOP2027Instance, CGSHOP2027Solution, CutterTour
from ortools.sat.python import cp_model

Point = tuple[int, int]


class UnsupportedInstanceError(ValueError):
    """A valid instance lies outside the exact oracle's supported scope."""


@dataclass(frozen=True)
class Bounds:
    left: int
    bottom: int
    right: int
    top: int

    @property
    def area(self) -> int:
        return (self.right - self.left) * (self.top - self.bottom)


def rectangle_bounds(xs: list[int], ys: list[int], label: str) -> Bounds:
    """Accept rectangles with extra collinear vertices, but not indentations."""
    bounds = Bounds(min(xs), min(ys), max(xs), max(ys))
    points = list(zip(xs, ys, strict=True))
    twice_area = abs(sum(
        x * next_y - next_x * y
        for (x, y), (next_x, next_y) in zip(points, points[1:] + points[:1])
    ))
    # The instance schema already validates polygon simplicity and rectilinearity.
    if bounds.area <= 0 or twice_area != 2 * bounds.area:
        raise UnsupportedInstanceError(f"{label} must be an axis-aligned rectangle")
    return bounds


@dataclass(frozen=True)
class Grid:
    positions: tuple[Point, ...]
    cells: tuple[Point, ...]
    covering_positions: tuple[tuple[int, ...], ...]
    arcs: tuple[tuple[int, int], ...]


def build_grid(
    instance: CGSHOP2027Instance,
    *,
    max_positions: int = 20,
    max_cells: int = 36,
) -> Grid:
    """Build the complete grid; never silently sample or truncate positions."""
    if max_positions < 1 or max_cells < 1:
        raise ValueError("Grid limits must be positive")
    if instance.number_of_cutters != 1:
        raise UnsupportedInstanceError("The oracle requires exactly one cutter")
    if instance.region_to_cover.inner_boundaries:
        raise UnsupportedInstanceError("The lawn must not contain holes")
    boundary = instance.region_to_cover.outer_boundary
    lawn = rectangle_bounds(boundary.x, boundary.y, "Lawn")
    shape = rectangle_bounds(instance.cutter.x, instance.cutter.y, "Cutter")
    cx, cy = instance.cutter_center
    cutter = Bounds(shape.left - cx, shape.bottom - cy, shape.right - cx, shape.top - cy)

    if lawn.area > max_cells:
        raise UnsupportedInstanceError(f"Lawn has {lawn.area} cells; limit is {max_cells}")
    # Exactly the integer placements with positive-area intersection with the lawn.
    x_min, x_max = lawn.left - cutter.right + 1, lawn.right - cutter.left - 1
    y_min, y_max = lawn.bottom - cutter.top + 1, lawn.top - cutter.bottom - 1
    count = (x_max - x_min + 1) * (y_max - y_min + 1)
    if count > max_positions:
        raise UnsupportedInstanceError(f"Grid has {count} candidate center positions; limit is {max_positions}")

    positions = tuple((x, y) for y in range(y_min, y_max + 1) for x in range(x_min, x_max + 1))
    cells = tuple((x, y) for y in range(lawn.bottom, lawn.top) for x in range(lawn.left, lawn.right))
    covering = tuple(
        tuple(i for i, (px, py) in enumerate(positions)
              if px + cutter.left <= x < px + cutter.right
              and py + cutter.bottom <= y < py + cutter.top)
        for x, y in cells
    )
    index = {point: i for i, point in enumerate(positions)}
    arcs = tuple(
        (i, index[neighbor])
        for i, (x, y) in enumerate(positions)
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
        if neighbor in index
    )
    return Grid(positions, cells, covering, arcs)


@dataclass
class WalkModel:
    model: cp_model.CpModel
    used: list[cp_model.IntVar]
    root: list[cp_model.IntVar]
    traversed: dict[tuple[int, int], cp_model.IntVar]


def build_model(grid: Grid) -> WalkModel:
    """Select one connected balanced directed graph, allowing a single vertex."""
    model = cp_model.CpModel()
    n = len(grid.positions)
    used = [model.new_bool_var(f"visit_{v}") for v in range(n)]
    root = [model.new_bool_var(f"root_{v}") for v in range(n)]
    traversed = {arc: model.new_bool_var(f"edge_{arc[0]}_{arc[1]}") for arc in grid.arcs}
    flow = {arc: model.new_int_var(0, n, f"flow_{arc[0]}_{arc[1]}") for arc in grid.arcs}
    supply = [model.new_int_var(0, n, f"supply_{v}") for v in range(n)]
    incoming = [[] for _ in range(n)]
    outgoing = [[] for _ in range(n)]
    for arc, selected in traversed.items():
        u, v = arc
        outgoing[u].append(arc)
        incoming[v].append(arc)
        model.add(selected <= used[u])
        model.add(selected <= used[v])
        model.add(flow[arc] <= n * selected)

    model.add(sum(root) == 1)
    model.add(sum(supply) == sum(used))
    # A tour must cover the first cell, so it can start at one of its coverers.
    first_cell_coverers = set(grid.covering_positions[0])
    for v in range(n):
        in_degree = sum(traversed[a] for a in incoming[v])
        out_degree = sum(traversed[a] for a in outgoing[v])
        model.add(in_degree == out_degree)
        model.add(used[v] <= out_degree + root[v])
        model.add(root[v] <= used[v])
        if v not in first_cell_coverers:
            model.add(root[v] == 0)
        model.add(supply[v] <= n * root[v])
        # Only the root injects flow; every visited vertex consumes one unit.
        model.add(supply[v] + sum(flow[a] for a in incoming[v])
                  - sum(flow[a] for a in outgoing[v]) == used[v])

    for coverers in grid.covering_positions:
        model.add(sum(used[v] for v in coverers) >= 1)
    model.minimize(sum(traversed.values()))
    return WalkModel(model, used, root, traversed)


def extract_tour(grid: Grid, walk: WalkModel, backend: cp_model.CpSolver) -> CutterTour:
    """Hierholzer's algorithm, with the repeated closing point omitted."""
    start = next(v for v, chosen in enumerate(walk.root) if backend.value(chosen))
    successors: list[list[int]] = [[] for _ in grid.positions]
    for (u, v), selected in walk.traversed.items():
        if backend.value(selected):
            successors[u].append(v)
    stack = [start]
    circuit = []
    while stack:
        v = stack[-1]
        if successors[v]:
            stack.append(successors[v].pop())
        else:
            circuit.append(stack.pop())
    circuit.reverse()
    if len(circuit) > 1:
        circuit.pop()  # Competition tours close implicitly.
    points = [grid.positions[v] for v in circuit]
    return CutterTour(x=[x for x, _ in points], y=[y for _, y in points])


@dataclass(frozen=True)
class SolveResult:
    solution: CGSHOP2027Solution | None
    status: str
    proved_optimal: bool
    objective: int | None
    best_bound: float | None
    wall_time_seconds: float
    candidate_positions: int
    required_cells: int

    def report(self) -> dict[str, str | bool | int | float | None]:
        """JSON-ready diagnostics, also available when no incumbent exists."""
        return {
            "algorithm": "rectangular-grid CP-SAT",
            "status": self.status,
            "proved_optimal": self.proved_optimal,
            "objective": self.objective,
            "best_bound": self.best_bound,
            "wall_time_seconds": self.wall_time_seconds,
            "candidate_positions": self.candidate_positions,
            "required_cells": self.required_cells,
        }


def solve(
    instance: CGSHOP2027Instance,
    *,
    time_limit: float = 50.0,
    max_positions: int = 20,
    max_cells: int = 36,
) -> SolveResult:
    """Solve within the backend time limit, preserving CP-SAT's exact status.

    Unsupported instances raise ValueError. UNKNOWN/INFEASIBLE/MODEL_INVALID
    return diagnostics without a solution; FEASIBLE is never called optimal.
    """
    if not isfinite(time_limit) or time_limit <= 0:
        raise ValueError("Time limit must be finite and positive")
    grid = build_grid(instance, max_positions=max_positions, max_cells=max_cells)
    walk = build_model(grid)
    backend = cp_model.CpSolver()
    backend.parameters.max_time_in_seconds = time_limit
    backend.parameters.num_search_workers = 1
    backend.parameters.random_seed = 0
    status = backend.solve(walk.model)
    has_solution = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    solution = None
    if has_solution:
        solution = CGSHOP2027Solution(
            instance_uid=instance.instance_uid,
            tours=[extract_tour(grid, walk, backend)],
        )
    result = SolveResult(
        solution=solution,
        status=backend.status_name(status),
        proved_optimal=status == cp_model.OPTIMAL,
        objective=round(backend.objective_value) if has_solution else None,
        best_bound=backend.best_objective_bound if status in (
            cp_model.OPTIMAL, cp_model.FEASIBLE, cp_model.UNKNOWN
        ) else None,
        wall_time_seconds=backend.wall_time,
        candidate_positions=len(grid.positions),
        required_cells=len(grid.cells),
    )
    if solution is not None:
        if solution.objective != result.objective:
            raise RuntimeError("Extracted tour length differs from the model objective")
        solution.meta.update(result.report())
    return result
