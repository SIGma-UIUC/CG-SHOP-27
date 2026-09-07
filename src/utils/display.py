"""Display a solution's routes and coverage, or save the plot to a file."""

import argparse
from pathlib import Path

import matplotlib

from cgshop2027_pyutils.io import read_instance, read_solution


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Instance JSON file")
    parser.add_argument("sol", type=Path, help="Solution JSON file")
    parser.add_argument("--output", type=Path, help="Save a plot instead of opening a window")
    args = parser.parse_args()

    if args.output:
        matplotlib.use("Agg")

    import matplotlib.pyplot as plt
    from cgshop2027_pyutils.visualize import create_solution_plot

    instance = read_instance(args.input)
    solution = read_solution(args.sol)
    if instance.instance_uid != solution.instance_uid:
        parser.error("The instance and solution must have the same instance_uid.")

    fig = create_solution_plot(instance, solution)
    print("Longest route:", solution.max_tour_length)
    if args.output:
        fig.savefig(args.output, dpi=150)
        print(f"Saved plot to {args.output}")
        plt.close(fig)
    else:
        plt.show()


if __name__ == "__main__":
    main()
