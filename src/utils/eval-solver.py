"""Validate saved solutions; compatibility entry point for benchmark helpers."""

import argparse
from pathlib import Path
import runpy
import sys


def main() -> int:
    # benchmark-run.py invokes these two internal modes in isolated processes.
    if len(sys.argv) > 1 and sys.argv[1] in ('--validate', '--animate'):
        runpy.run_path(Path(__file__).with_name('benchmark-run.py'), run_name='__main__')
        return 0

    from cgshop2027_pyutils.io import read_instance, read_solution
    from cgshop2027_pyutils.verify import check_for_errors
    from pydantic import ValidationError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('instances', type=Path)
    parser.add_argument('solutions', type=Path)
    args = parser.parse_args()
    instances = {path.name.removesuffix('.instance.json'): path for path in args.instances.glob('*.instance.json')}
    solutions = {path.name.removesuffix('.solution.json'): path for path in args.solutions.glob('*.solution.json')}
    failures = 0
    for uid in sorted(instances.keys() & solutions.keys()):
        try:
            errors = check_for_errors(read_instance(instances[uid]), read_solution(solutions[uid]))
        except ValidationError as error:
            errors = [str(error)]
        if errors:
            failures += 1
            print(f'=== {uid}: {len(errors)} errors ===', *errors, sep='\n')
    mismatches = instances.keys() ^ solutions.keys()
    print(f'=== {failures} failures, {len(mismatches)} mismatches ===')
    return 1 if failures or mismatches else 0


if __name__ == '__main__':
    sys.exit(main())
