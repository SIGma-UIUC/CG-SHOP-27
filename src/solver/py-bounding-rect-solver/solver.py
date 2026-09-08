from math import ceil
from typing import NamedTuple, Self

from more_itertools import divide, flatten, unique_justseen

from cgshop2027_pyutils.schemas import (
    CGSHOP2027Instance,
    CGSHOP2027Solution,
    CutterTour,
)


class Rect(NamedTuple):
    left: int
    bottom: int
    right: int
    top: int

    @property
    def height(self) -> int:
        return self.top - self.bottom + 1

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @classmethod
    def enclosing(cls, xs: list[int], ys: list[int], offset=(0, 0)) -> Self:
        offset_x, offset_y = offset
        return cls(
            min(xs) - offset_x,
            min(ys) - offset_y,
            max(xs) - 1 - offset_x,
            max(ys) - 1 - offset_y,
        )


def solve(instance: CGSHOP2027Instance) -> CGSHOP2027Solution:
    boundary = instance.region_to_cover.outer_boundary
    lawn = Rect.enclosing(boundary.x, boundary.y)
    cutter = Rect.enclosing(instance.cutter.x, instance.cutter.y, instance.cutter_center)

    x_start, x_end = lawn.left - cutter.right, lawn.right - cutter.left
    strip_count = max(ceil(lawn.height / cutter.height), instance.number_of_cutters)
    anchor_rows = [lawn.top - cutter.top - i * cutter.height for i in range(strip_count)]

    tours = []
    for block in divide(instance.number_of_cutters, anchor_rows):
        tours.append(tour(list(block), x_start, x_end))

    return CGSHOP2027Solution(
        instance_uid=instance.instance_uid,
        tours=tours,
        meta={"algorithm": "bounding-rect strips"},
    )


def tour(anchor_rows: list[int], x_start: int, x_end: int) -> CutterTour:
    points = list(unique_justseen(flatten(
                  ((x_start, y), (x_end, y), (x_start, y)) for y in anchor_rows)))
    return CutterTour(x=[x for x, _ in points], y=[y for _, y in points])
