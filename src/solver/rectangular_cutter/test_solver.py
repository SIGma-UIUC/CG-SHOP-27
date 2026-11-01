import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cgshop2027_pyutils.grid import rasterize, rasterize_ring
from cgshop2027_pyutils.io import read_solution
from cgshop2027_pyutils.schemas import CGSHOP2027Instance
from cgshop2027_pyutils.schemas.instance import PointSequence, PolyominoWithHoles
from cgshop2027_pyutils.verify import SolutionValidator

from main import main
from solver import _build_candidate_centers, solve


def ring(points: list[tuple[int, int]]) -> PointSequence:
    return PointSequence(
        x=[x for x, _ in points],
        y=[y for _, y in points],
    )


def instance(
    region: PointSequence,
    cutter: PointSequence | None = None,
    number_of_cutters: int = 1,
    cutter_center: tuple[int, int] = (0, 0),
) -> CGSHOP2027Instance:
    return CGSHOP2027Instance(
        instance_uid="test",
        region_to_cover=PolyominoWithHoles(
            outer_boundary=region,
            inner_boundaries=[],
        ),
        cutter=cutter or ring([(0, 0), (1, 0), (1, 1), (0, 1)]),
        cutter_center=cutter_center,
        number_of_cutters=number_of_cutters,
    )


class ExactSolverTests(unittest.TestCase):
    def test_one_cell_region_stays_in_place(self) -> None:
        problem = instance(ring([(0, 0), (1, 0), (1, 1), (0, 1)]))

        solution = solve(problem)

        self.assertEqual(solution.max_tour_length, 0)
        self.assertTrue(solution.meta["optimal"])
        self.assertEqual(SolutionValidator(problem).check_for_errors(solution), [])

    def test_fixed_cutter_center_is_used_as_local_offset(self) -> None:
        problem = instance(
            ring([(0, 0), (1, 0), (1, 1), (0, 1)]),
            cutter_center=(1, 1),
        )

        solution = solve(problem)

        self.assertEqual(list(solution.tours[0].points()), [(1, 1)])
        self.assertEqual(SolutionValidator(problem).check_for_errors(solution), [])

    def test_two_cells_have_minimum_closed_tour(self) -> None:
        problem = instance(ring([(0, 0), (2, 0), (2, 1), (0, 1)]))

        solution = solve(problem)

        self.assertEqual(solution.max_tour_length, 2)
        self.assertTrue(solution.meta["optimal"])
        self.assertEqual(SolutionValidator(problem).check_for_errors(solution), [])

    def test_rejects_more_than_one_cutter(self) -> None:
        problem = instance(
            ring([(0, 0), (1, 0), (1, 1), (0, 1)]),
            number_of_cutters=2,
        )

        with self.assertRaisesRegex(ValueError, "exactly 2"):
            solve(problem)

    def test_twenty_cell_region_solves_at_candidate_limit(self) -> None:
        problem = instance(ring([(0, 0), (20, 0), (20, 1), (0, 1)]))

        solution = solve(problem)

        self.assertEqual(solution.max_tour_length, 38)
        self.assertTrue(solution.meta["optimal"])
        self.assertEqual(SolutionValidator(problem).check_for_errors(solution), [])

    def test_rejects_more_than_two_hundred_candidate_centers(self) -> None:
        problem = instance(ring([(0, 0), (201, 0), (201, 1), (0, 1)]))

        with self.assertRaisesRegex(ValueError, "at most 200 candidate cutter centers"):
            solve(problem)

    def test_accepts_non_rectangular_cutter(self) -> None:
        cutter = ring([(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)])
        problem = instance(
            ring([(0, 0), (1, 0), (1, 1), (0, 1)]),
            cutter=cutter,
        )

        solution = solve(problem)

        self.assertEqual(SolutionValidator(problem).check_for_errors(solution), [])

    def test_movement_grid_includes_non_covering_transit_positions(self) -> None:
        problem = CGSHOP2027Instance(
            instance_uid="donut",
            region_to_cover=PolyominoWithHoles(
                outer_boundary=ring([(0, 0), (3, 0), (3, 3), (0, 3)]),
                inner_boundaries=[ring([(1, 1), (1, 2), (2, 2), (2, 1)])],
            ),
            cutter=ring([(0, 0), (1, 0), (1, 1), (0, 1)]),
            cutter_center=(0, 0),
            number_of_cutters=1,
        )
        region_cells = set(rasterize(problem.region_to_cover).cells())
        cutter_cells = set(rasterize_ring(problem.cutter).cells())

        centers, covering_centers = _build_candidate_centers(
            problem, region_cells, cutter_cells
        )

        transit_index = centers.index((1, 1))
        self.assertEqual(len(centers), 9)
        self.assertNotIn(transit_index, [i for indices in covering_centers.values() for i in indices])
        solution = solve(problem)
        self.assertEqual(solution.max_tour_length, 8)
        self.assertEqual(SolutionValidator(problem).check_for_errors(solution), [])

    def test_cli_writes_standard_solution_json(self) -> None:
        problem = instance(ring([(0, 0), (1, 0), (1, 1), (0, 1)]))
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.instance.json"
            output_path = Path(directory) / "output.solution.json"
            input_path.write_text(problem.model_dump_json(), encoding="utf-8")

            with (
                patch.object(
                    sys,
                    "argv",
                    ["main.py", str(input_path), str(output_path)],
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                main()

            serialized = json.loads(output_path.read_text(encoding="utf-8"))
            solution = read_solution(output_path)

        self.assertEqual(serialized["content_type"], "CGSHOP2027_Solution")
        self.assertTrue(solution.meta["optimal"])
        self.assertEqual(SolutionValidator(problem).check_for_errors(solution), [])


if __name__ == "__main__":
    unittest.main()
