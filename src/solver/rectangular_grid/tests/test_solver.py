"""Analytic, exhaustive, competition-verifier, and CLI checks."""

from collections import deque
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from cgshop2027_pyutils.schemas import CGSHOP2027Instance
from cgshop2027_pyutils.verify import check_for_errors
import pytest
from shapely.geometry import box

from solver import build_grid, solve

ROOT = Path(__file__).resolve().parents[1]


def rectangle(width, height, origin=(0, 0)):
    x, y = origin
    return {"x": [x, x + width, x + width, x], "y": [y, y, y + height, y + height]}


def instance(width, height, cutter_width=1, cutter_height=1, *,
             origin=(0, 0), cutter_origin=(0, 0), center=None):
    return CGSHOP2027Instance.model_validate({
        "instance_uid": "tiny",
        "region_to_cover": {"outer_boundary": rectangle(width, height, origin), "inner_boundaries": []},
        "cutter": rectangle(cutter_width, cutter_height, cutter_origin),
        "cutter_center": center if center is not None else cutter_origin,
        "number_of_cutters": 1,
    })


def checked_solve(problem, **kwargs):
    result = solve(problem, **kwargs)
    assert result.status == "OPTIMAL"
    assert result.proved_optimal
    assert result.objective == result.best_bound
    assert result.solution is not None
    assert result.solution.objective == result.objective
    assert check_for_errors(problem, result.solution) == []
    return result


@pytest.mark.parametrize("width,height,cw,ch,optimum", [
    (1, 1, 1, 1, 0), (4, 1, 1, 1, 6), (1, 4, 1, 1, 6),
    (2, 2, 1, 1, 4), (3, 3, 1, 1, 10), (4, 4, 1, 1, 16),
    (5, 4, 1, 1, 20), (2, 2, 2, 2, 0), (2, 1, 3, 2, 0),
    (3, 2, 2, 2, 2), (3, 3, 2, 2, 4),
])
def test_analytic_optima(width, height, cw, ch, optimum):
    assert checked_solve(instance(width, height, cw, ch)).objective == optimum


def exhaustive_closed_walk(problem):
    """Independent BFS over (position, covered-cell mask), with all starts.

    Coverage uses geometric containment, not the CP model's coverage table.
    Repeated edges/vertices are unrestricted; the first full-cover return is
    shortest for that start. Only the justified finite position box is shared.
    """
    grid = build_grid(problem)
    positions = grid.positions
    cutter = problem.cutter
    cx, cy = problem.cutter_center
    masks = []
    for x, y in positions:
        footprint = box(min(cutter.x) + x - cx, min(cutter.y) + y - cy,
                        max(cutter.x) + x - cx, max(cutter.y) + y - cy)
        masks.append(sum(1 << i for i, (a, b) in enumerate(grid.cells)
                         if footprint.covers(box(a, b, a + 1, b + 1))))
    neighbors = [
        [j for j, (a, b) in enumerate(positions) if abs(x - a) + abs(y - b) == 1]
        for x, y in positions
    ]
    full = (1 << len(grid.cells)) - 1
    best = float("inf")
    for start in range(len(positions)):
        queue = deque([(start, masks[start], 0)])
        seen = {(start, masks[start])}
        while queue:
            position, covered, length = queue.popleft()
            if position == start and covered == full:
                best = min(best, length)
                break
            if length >= best:
                continue
            for neighbor in neighbors[position]:
                state = (neighbor, covered | masks[neighbor])
                if state not in seen:
                    seen.add(state)
                    queue.append((*state, length + 1))
    return best


@pytest.mark.parametrize("width,height,cw,ch", [
    (w, h, cw, ch) for w in range(1, 4) for h in range(1, 4)
    for cw in range(1, 3) for ch in range(1, 3)
])
def test_matches_exhaustive_walks(width, height, cw, ch):
    problem = instance(width, height, cw, ch)
    assert checked_solve(problem).objective == exhaustive_closed_walk(problem)


def test_translation_and_center_offset():
    problem = instance(3, 3, 2, 2, origin=(-7, 11), cutter_origin=(8, -5), center=(9, -4))
    assert checked_solve(problem).objective == 4


def test_exterior_centers_are_available():
    problem = instance(2, 1, 3, 1)
    grid = build_grid(problem)
    assert (-2, 0) in grid.positions
    assert (-1, 0) in grid.positions
    assert checked_solve(problem).objective == 0


def test_collinear_boundary_vertices():
    problem = instance(2, 2)
    data = problem.model_dump()
    data["region_to_cover"]["outer_boundary"] = {"x": [0, 1, 2, 2, 0], "y": [0, 0, 0, 2, 2]}
    assert checked_solve(CGSHOP2027Instance.model_validate(data)).objective == 4


@pytest.mark.parametrize("field", ["lawn", "cutter", "holes", "count"])
def test_rejects_unsupported_geometry(field):
    data = instance(3, 3).model_dump()
    nonrectangle = {"x": [0, 2, 2, 1, 1, 0], "y": [0, 0, 1, 1, 2, 2]}
    if field == "lawn":
        data["region_to_cover"]["outer_boundary"] = nonrectangle
    elif field == "cutter":
        data["cutter"] = nonrectangle
    elif field == "holes":
        data["region_to_cover"]["inner_boundaries"] = [{"x": [1, 1, 2, 2], "y": [1, 2, 2, 1]}]
    else:
        data["number_of_cutters"] = 2
    with pytest.raises(ValueError):
        solve(CGSHOP2027Instance.model_validate(data))


def test_limits_and_overrides():
    with pytest.raises(ValueError, match="candidate center positions"):
        solve(instance(5, 5))
    with pytest.raises(ValueError, match="cells"):
        solve(instance(37, 1))
    assert checked_solve(instance(21, 1), max_positions=21).objective == 40
    assert checked_solve(instance(37, 1), max_positions=37, max_cells=37).objective == 72
    with pytest.raises(ValueError, match="positive"):
        solve(instance(1, 1), max_cells=0)


@pytest.mark.parametrize("limit", [0, -1, float("inf"), float("nan")])
def test_invalid_time_limits(limit):
    with pytest.raises(ValueError, match="Time limit"):
        solve(instance(1, 1), time_limit=limit)


def test_timeout_without_incumbent():
    result = solve(instance(4, 4), time_limit=1e-9)
    assert result.status == "UNKNOWN"
    assert not result.proved_optimal
    assert result.solution is None
    assert result.objective is None
    json.dumps(result.report(), allow_nan=False)


@pytest.mark.parametrize("width,height,cw,ch", [(3, 2, 1, 1), (2, 3, 1, 2), (3, 3, 2, 2)])
def test_no_worse_than_existing_strip_solver(width, height, cw, ch):
    path = ROOT.parent / "py-bounding-rect-solver" / "solver.py"
    spec = importlib.util.spec_from_file_location("strip_solver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    problem = instance(width, height, cw, ch)
    baseline = module.solve(problem)
    assert check_for_errors(problem, baseline) == []
    assert checked_solve(problem).objective <= baseline.objective


def test_cli_writes_verified_solution_and_report(tmp_path):
    source = tmp_path / "tiny.instance.json"
    source.write_text(instance(2, 2).model_dump_json())
    output = tmp_path / "results"
    command = [sys.executable, str(ROOT / "main.py"), str(output), "--instances", str(source)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    report = json.loads((output / "report.json").read_text())[0]
    assert report["proved_optimal"] and report["objective"] == 4
    assert (output / "tiny.solution.json").exists()
    # A failed rerun must not retain an apparently successful stale solution.
    completed = subprocess.run(command + ["--max-positions", "1"], capture_output=True, text=True)
    assert completed.returncode == 1
    assert not (output / "tiny.solution.json").exists()
    assert json.loads((output / "report.json").read_text())[0]["status"] == "UNSUPPORTED"
    assert "Generated 0/1 solutions" in completed.stderr


def test_disconnected_cycles_are_infeasible():
    from ortools.sat.python import cp_model
    from solver import build_model

    grid = build_grid(instance(4, 2))
    walk = build_model(grid)
    index = {point: i for i, point in enumerate(grid.positions)}
    selected = set()
    for left in (0, 2):
        cycle = [(left, 0), (left + 1, 0), (left + 1, 1), (left, 1)]
        selected.update((index[a], index[b]) for a, b in zip(cycle, cycle[1:] + cycle[:1]))
    for arc, variable in walk.traversed.items():
        walk.model.add(variable == int(arc in selected))
    assert cp_model.CpSolver().solve(walk.model) == cp_model.INFEASIBLE


def test_feasible_incumbent_is_not_reported_as_optimal(monkeypatch):
    from ortools.sat.python import cp_model

    class FeasibleBackend(cp_model.CpSolver):
        """Exercise status handling without relying on machine-specific timing."""
        def solve(self, model, *args, **kwargs):
            assert super().solve(model, *args, **kwargs) == cp_model.OPTIMAL
            return cp_model.FEASIBLE

    monkeypatch.setattr(cp_model, "CpSolver", FeasibleBackend)
    problem = instance(2, 2)
    result = solve(problem)
    assert result.status == "FEASIBLE"
    assert not result.proved_optimal
    assert result.solution.meta["proved_optimal"] is False
    assert check_for_errors(problem, result.solution) == []


def test_tour_can_stay_outside_lawn():
    from ortools.sat.python import cp_model
    from solver import build_model, extract_tour
    from cgshop2027_pyutils.schemas import CGSHOP2027Solution

    problem = instance(2, 1, 3, 1)
    grid = build_grid(problem)
    walk = build_model(grid)
    walk.model.add(walk.root[grid.positions.index((-1, 0))] == 1)
    backend = cp_model.CpSolver()
    assert backend.solve(walk.model) == cp_model.OPTIMAL
    tour = extract_tour(grid, walk, backend)
    assert tour.start == (-1, 0) and tour.length == 0
    solution = CGSHOP2027Solution(instance_uid=problem.instance_uid, tours=[tour])
    assert check_for_errors(problem, solution) == []
