"""Plot or animate a solution's routes and coverage."""

import argparse
from pathlib import Path

import matplotlib

from cgshop2027_pyutils.io import read_instance, read_solution


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Instance JSON file")
    parser.add_argument("sol", type=Path, help="Solution JSON file")
    parser.add_argument("--animate", action="store_true", help="Animate the cutters moving along their routes")
    parser.add_argument("--output", type=Path, help="Save instead of opening a window (use .gif with --animate)")
    args = parser.parse_args()

    if args.animate and args.output and args.output.suffix.lower() != ".gif":
        parser.error("Animated output must use a .gif filename.")

    if args.output:
        matplotlib.use("Agg")

    import matplotlib.pyplot as plt
    from cgshop2027_pyutils.visualize import create_solution_animation, create_solution_plot

    instance = read_instance(args.input)
    solution = read_solution(args.sol)
    if instance.instance_uid != solution.instance_uid:
        parser.error("The instance and solution must have the same instance_uid.")

    print("Longest route:", solution.max_tour_length)
    if args.animate:
        # Keep a reference alive until the window closes or saving finishes.
        animation = create_solution_animation(instance, solution)
        if args.output:
            animation.save(args.output, writer="pillow", dpi=80)
            print(f"Saved animation to {args.output}")
            plt.close("all")
        else:
            plt.show()
        return

    fig = create_solution_plot(instance, solution)
    if args.output:
        fig.savefig(args.output, dpi=150)
        print(f"Saved plot to {args.output}")
        plt.close(fig)
    else:
        plt.show()


if __name__ == "__main__":
    main()
