"""
TODO: how should we evaluate instances?

- having an instance generator in utils would be great
- running it on the examples and writing basic summary statistics would be great
"""

import argparse
from pathlib import Path

from cgshop2027_pyutils.io import read_instance, read_solution
from cgshop2027_pyutils.verify import check_for_errors
from pydantic import ValidationError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("instances", type=Path)
    parser.add_argument("solutions", type=Path)
    args = parser.parse_args()

    instances = {
        path.name.removesuffix(".instance.json"): path
        for path in args.instances.glob("*.instance.json")
    }
    solutions = {
        path.name.removesuffix(".solution.json"): path
        for path in args.solutions.glob("*.solution.json")
    }
    mismatches = instances.keys() ^ solutions.keys()

    failures = 0
    for uid in sorted(instances.keys() & solutions.keys()):
        try:
            errors = check_for_errors(
                read_instance(instances[uid]),
                read_solution(solutions[uid]),
            )
        except ValidationError as error:
            errors = [str(error)]
        if errors:
            failures += 1
            print(f"=== {uid}: {len(errors)} errors ===", *errors, sep="\n")

    print(f"=== {failures} failures, {len(mismatches)} mismatches ===")


if __name__ == "__main__":
    main()
