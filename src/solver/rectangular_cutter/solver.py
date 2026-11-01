from ortools.sat.python import cp_model

from cgshop2027_pyutils.grid import rasterize, rasterize_ring
from cgshop2027_pyutils.schemas import (
    CGSHOP2027Instance,
    CGSHOP2027Solution,
    CutterTour,
)
from cgshop2027_pyutils.verify import SolutionValidator

MAX_DURATION = 50.0 

"""
Returns a list of allowed center positions for the cutter.
Covering_centers maps a point to a list of cutter center indices that will cover the point
"""
def _center_candidates(
    instance: CGSHOP2027Instance,
    region_cells: set[tuple[int, int]],
    cutter_cells: set[tuple[int, int]],
) -> tuple[list[tuple[int, int]], dict[tuple[int, int], list[int]]]:
    center_x, center_y = instance.cutter_center
    offsets = sorted((x-center_x, y-center_y) for x, y in cutter_cells)
    covering_positions = set()
    for cell_x, cell_y in region_cells:
        for offset_x, offset_y in offsets:
            covering_positions.add((cell_x-offset_x, cell_y-offset_y))

    min_x = min(x for x, _ in covering_positions)
    max_x = max(x for x, _ in covering_positions)
    min_y = min(y for _, y in covering_positions)
    max_y = max(y for _, y in covering_positions)
    
    # Represents the smallest bounding box containing all covering_positions
    centers = [(x, y) for x in range(min_x, max_x+1) for y in range(min_y, max_y+1)]
    
    # Maps cell to list of cutter centers that will cover it
    cell_coverage = {}
    center_index = {center: index for index, center in enumerate(centers)}
    for cell_x, cell_y in region_cells:
        indices = []
        for offset_x, offset_y in offsets:
            center_pos = (cell_x-offset_x, cell_y-offset_y)
            index = center_index[center_pos]
            indices.append(index)
        cell_coverage[(cell_x, cell_y)] = indices
    return centers, cell_coverage


"""
Returns a list of valid transitions (a,b,c) where a,b are indices of of centers and 
c is the boolean for whether the cutter moved or not
"""
def _allowed_transitions(centers: list[tuple[int, int]]) -> list[tuple[int, int, int]]:
    center_index = {center: index for index, center in enumerate(centers)}
    transitions = []
    for start, (x, y) in enumerate(centers):
        for neighbor in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
            end = center_index.get(neighbor)
            if end is not None:
                transitions.append((start, end, 1))
    stationary = [(center, center, 0) for center in range(len(centers))]
    return transitions + stationary


"""
Reconstructs the coordinate path of the cutter
"""
def _make_tour(
    solver: cp_model.CpSolver,
    positions: list[cp_model.IntVar],
    centers: list[tuple[int, int]],
    length: int,
) -> CutterTour:
    x_coords, y_coords = [], []
    for position in positions[:length+1]:
        center_index = solver.Value(position)
        x, y = centers[center_index]
        x_coords.append(x)
        y_coords.append(y)
    return CutterTour(x=x_coords, y=y_coords)


def solve(instance: CGSHOP2027Instance) -> CGSHOP2027Solution:
    region_cells = set(rasterize(instance.region_to_cover).cells())
    cutter_cells = set(rasterize_ring(instance.cutter).cells())
    centers, cell_coverage = _center_candidates(instance, region_cells, cutter_cells)
    transitions = _allowed_transitions(centers) 
    
    model = cp_model.CpModel()
    max_steps = max(1, 2*(len(centers)-1)) # 2 * number of edges in spanning tree
    tour_length = model.NewIntVar(0, max_steps, "tour_length")
    
    # Lists representing cutter positions and whether its moving at each step
    positions = [model.NewIntVar(0, len(centers)-1, f"pos_{step}") for step in range(max_steps+1)]
    is_moving = [model.NewBoolVar(f"moving_{step}") for step in range(max_steps)]
    
    # Enforce positions/is_moving changes are apart of a valid transition
    for step in range(max_steps):
        model.AddAllowedAssignments(
            [positions[step], positions[step+1], is_moving[step]],
            transitions,
        )
        if step:
            model.Add(is_moving[step-1] >= is_moving[step])
            
    # Enforces that every region in the cell gets covered at least once
    for cell_index, covering_indices in enumerate(cell_coverage.values()):
        covered_steps = [] 
        valid_positions = [(center,) for center in covering_indices]
        for step, position in enumerate(positions):
            covered = model.NewBoolVar(f"covered_{cell_index}_{step}")
            model.AddAllowedAssignments([position], valid_positions).OnlyEnforceIf(covered)
            covered_steps.append(covered)
        model.Add(sum(covered_steps) >= 1)
        
    # Enforce other constraints
    model.Add(positions[0] == positions[max_steps])
    model.Add(sum(is_moving) == tour_length) 
    model.AddElement(tour_length, positions, positions[0]) 
    model.Minimize(tour_length)
    
    # Configuring the solver and returning the solution
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = MAX_DURATION
    status = solver.Solve(model)
    
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise TimeoutError(f"No solution found within {MAX_DURATION:g} seconds.")

    solution = CGSHOP2027Solution(
        instance_uid=instance.instance_uid,
        tours=[_make_tour(solver, positions, centers, solver.Value(tour_length))],
        meta={"algorithm": "rectangular_cutter cp-sat"},
    )
    
    errors = SolutionValidator(instance).check_for_errors(solution) 
    if errors:
        raise ValueError("Solver produced an invalid solution:\n" + "\n".join(errors))
    return solution