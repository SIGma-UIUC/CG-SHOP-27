"""Solve a small single-rectangular-cutter instance exactly."""

import argparse
from pathlib import Path

from cgshop2027_pyutils.io import read_instance

from solver import solve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Instance JSON file")
    parser.add_argument("output", type=Path, help="Output .solution.json file")
    args = parser.parse_args()

    try:
        solution = solve(read_instance(args.input))
    except (ValueError, TimeoutError) as error:
        parser.exit(1, f"{error}\n")

    args.output.write_text(solution.model_dump_json(), encoding="utf-8")
    print(f"Saved solution to {args.output}")
    print("Longest route:", solution.max_tour_length)
    print("Optimal:", solution.meta["optimal"])


if __name__ == "__main__":
    main()
