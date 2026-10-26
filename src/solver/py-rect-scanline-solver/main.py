import argparse
from pathlib import Path

from cgshop2027_pyutils.io import read_instance
from solver import solve

INSTANCES = Path(__file__).parent / "../../examples/test_instances1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--instances", type=Path, default=INSTANCES)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    for path in sorted(args.instances.glob("*.instance.json")):
        solution = solve(read_instance(path))
        destination = args.output / f"{solution.instance_uid}.solution.json"
        destination.write_text(solution.model_dump_json())
        print(solution.instance_uid)


if __name__ == "__main__":
    main()
