"""Solves an instance of the multi-robot lawn mowing problem and produces a solution."""

import argparse
from pathlib import Path

from cgshop2027_pyutils.io import read_instance
from cgshop2027_pyutils.schemas import (
    CGSHOP2027Instance,
    CGSHOP2027Solution,
    CutterTour,
)
from cgshop2027_pyutils.verify import SolutionValidator


def generate_tours(
    instance: CGSHOP2027Instance, validator: SolutionValidator
) -> list[CutterTour]:
    """TODO: return one closed tour per cutter that collectively cover the region.
    """
    raise NotImplementedError("Implement generate_tours() with your algorithm.")


def solve(instance: CGSHOP2027Instance) -> CGSHOP2027Solution:
    validator = SolutionValidator(instance)
    tours = generate_tours(instance, validator)
    solution = CGSHOP2027Solution(
        instance_uid=instance.instance_uid,
        tours=tours)

    # Schema validation checks the format; this checks coverage and tour count.
    errors = validator.check_for_errors(solution)
    if errors:
        raise ValueError("Invalid solution:\n" + "\n".join(errors))
    return solution


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Instance JSON file")
    parser.add_argument("output", type=Path, help="Output .solution.json file")
    args = parser.parse_args()

    try:
        solution = solve(read_instance(args.input))
    except (NotImplementedError, ValueError) as error:
        parser.exit(1, f"{error}\n")

    args.output.write_text(solution.model_dump_json(), encoding="utf-8")
    print(f"Saved solution to {args.output}")
    print("Longest route:", solution.max_tour_length)


if __name__ == "__main__":
    main()
