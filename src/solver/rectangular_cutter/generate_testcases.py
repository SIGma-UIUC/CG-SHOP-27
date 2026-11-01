"""Generate reproducible random one-cutter polyomino instances."""

import argparse
import random
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from cgshop2027_pyutils.schemas import CGSHOP2027Instance
from cgshop2027_pyutils.schemas.instance import PointSequence, PolyominoWithHoles


def _ring_to_sequence(ring) -> PointSequence:
    coordinates = list(ring.coords)[:-1]
    return PointSequence(
        x=[int(round(x)) for x, _ in coordinates],
        y=[int(round(y)) for _, y in coordinates],
    )


def _random_connected_grid(
    rng: random.Random, grid_width: int, grid_height: int, target_cells: int
) -> Polygon:
    if not 1 <= target_cells <= grid_width * grid_height:
        raise ValueError("target_cells must fit inside the requested grid.")

    start = (grid_width // 2, grid_height // 2)
    occupied = {start}
    frontier = set()

    def add_neighbors(cell: tuple[int, int]) -> None:
        x, y = cell
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbor = (x + dx, y + dy)
            if (
                0 <= neighbor[0] < grid_width
                and 0 <= neighbor[1] < grid_height
                and neighbor not in occupied
            ):
                frontier.add(neighbor)

    add_neighbors(start)
    while len(occupied) < target_cells and frontier:
        cell = rng.choice(tuple(frontier))
        frontier.remove(cell)
        occupied.add(cell)
        add_neighbors(cell)

    merged = unary_union([box(x, y, x + 1, y + 1) for x, y in occupied])
    if isinstance(merged, MultiPolygon):
        merged = max(merged.geoms, key=lambda polygon: polygon.area)
    return merged


def _rectangle_dimensions(target_cells: int) -> tuple[int, int]:
    if target_cells < 1:
        raise ValueError("target_cells must be positive.")

    width = int(target_cells**0.5)
    while target_cells % width:
        width -= 1
    return width, target_cells // width


def _rectangle_with_area(target_cells: int) -> Polygon:
    width, height = _rectangle_dimensions(target_cells)
    return box(0, 0, width, height)


def generate_random_testcase(
    instance_uid: str,
    seed: int,
    region_cells: int,
    cutter_cells: int = 7,
    region_grid_size: int = 30,
    cutter_grid_size: int = 6,
    rectangular_region: bool = False,
    rectangular_cutter: bool = False,
) -> CGSHOP2027Instance:
    rng = random.Random(seed)
    region_polygon = (
        _rectangle_with_area(region_cells)
        if rectangular_region
        else _random_connected_grid(
            rng, region_grid_size, region_grid_size, region_cells
        )
    )
    cutter_polygon = (
        _rectangle_with_area(cutter_cells)
        if rectangular_cutter
        else _random_connected_grid(
            rng, cutter_grid_size, cutter_grid_size, cutter_cells
        )
    )
    region_polygon = orient(region_polygon, sign=1.0)
    cutter_polygon = orient(cutter_polygon, sign=1.0)
    if rectangular_cutter:
        cutter_width, cutter_height = _rectangle_dimensions(cutter_cells)
        cutter_center = (cutter_width // 2, cutter_height // 2)
    else:
        cutter_center_point = cutter_polygon.representative_point()
        cutter_center = (int(cutter_center_point.x), int(cutter_center_point.y))

    return CGSHOP2027Instance(
        instance_uid=instance_uid,
        region_to_cover=PolyominoWithHoles(
            outer_boundary=_ring_to_sequence(region_polygon.exterior),
            inner_boundaries=[
                _ring_to_sequence(hole) for hole in region_polygon.interiors
            ],
        ),
        cutter=_ring_to_sequence(cutter_polygon.exterior),
        cutter_center=cutter_center,
        number_of_cutters=1,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Directory for generated instances")
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument(
        "--region-cells",
        type=int,
        nargs=3,
        default=[30, 40, 50],
        metavar=("FIRST", "SECOND", "THIRD"),
        help="Cell counts for the three instances (default: 30 40 50)",
    )
    parser.add_argument(
        "--cutter-cells",
        type=int,
        nargs=3,
        default=[7, 7, 7],
        metavar=("FIRST", "SECOND", "THIRD"),
        help="Cutter cell counts for the three instances (default: 7 7 7)",
    )
    parser.add_argument(
        "--region-grid-size",
        type=int,
        default=30,
        help="Width and height of the square region grid (default: 30)",
    )
    parser.add_argument(
        "--cutter-grid-size",
        type=int,
        default=6,
        help="Width and height of the square cutter grid (default: 6)",
    )
    parser.add_argument(
        "--rectangular-region",
        action="store_true",
        help="Make each region an axis-aligned rectangle with the requested area",
    )
    parser.add_argument(
        "--rectangular-cutter",
        action="store_true",
        help="Make each cutter an axis-aligned rectangle with the requested area",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    for index, (cell_count, cutter_cell_count) in enumerate(
        zip(args.region_cells, args.cutter_cells, strict=True)
    ):
        seed = args.seed + index
        region_shape = "rectangle_" if args.rectangular_region else ""
        instance = generate_random_testcase(
            instance_uid=(
                f"{region_shape}random_k1_seed{seed}_{cell_count}region_"
                f"{cutter_cell_count}cutter_cells"
            ),
            seed=seed,
            region_cells=cell_count,
            cutter_cells=cutter_cell_count,
            region_grid_size=args.region_grid_size,
            cutter_grid_size=args.cutter_grid_size,
            rectangular_region=args.rectangular_region,
            rectangular_cutter=args.rectangular_cutter,
        )
        destination = args.output / f"{instance.instance_uid}.instance.json"
        destination.write_text(instance.model_dump_json(indent=2), encoding="utf-8")
        print(
            f"Saved {destination}: {cell_count} region cells, "
            f"{cutter_cell_count} cutter cells, seed {seed}"
        )


if __name__ == "__main__":
    main()
