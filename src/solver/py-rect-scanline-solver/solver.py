from math import ceil
from typing import NamedTuple, Self

from more_itertools import divide, unique_justseen

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

def compute_rect_cutter(cutter, cutter_center):
    n = len(cutter.x)
    rows = {}
    
    for j in range(n):
        x1, y1 = cutter.x[j], cutter.y[j]
        x2, y2 = cutter.x[(j + 1) % n], cutter.y[(j + 1) % n]

        if y1 == y2:
            continue

        for row in range(min(y1, y2), max(y1, y2)):
            if row not in rows:
                rows[row] = []
            rows[row].append(x1)

    filled = set()
    for row, xs in rows.items():
        xs.sort()
        for k in range(0, len(xs), 2):
            for x in range(xs[k], xs[k + 1]):
                filled.add((x, row))

    best = (0, 0, 0, 0)
    best_area = 0
    min_col = min(x for x, y in filled)
    max_col = max(x for x, y in filled)
    min_row = min(y for x, y in filled)
    max_row = max(y for x, y in filled)

    for left in range(min_col, max_col + 1):
        for right in range(left, max_col + 1):
            for bottom in range(min_row, max_row + 1):
                for top in range(bottom, max_row + 1):
                    area = (right - left + 1) * (top - bottom + 1)
                    if area <= best_area:
                        continue
                    if all((c, r) in filled
                        for c in range(left, right + 1)
                        for r in range(bottom, top + 1)):
                        best, best_area = (left, bottom, right, top), area
    return Rect(best[0] - cutter_center[0], best[1] - cutter_center[1], best[2] - cutter_center[0], best[3] - cutter_center[1])
        

def row_spans(boundary):
    n = len(boundary.x)
    spans = {}

    for j in range(n):
        x1, y1 = boundary.x[j], boundary.y[j]
        x2, y2 = boundary.x[(j + 1) % n], boundary.y[(j + 1) % n]

        if y1 == y2:
            continue

        for row in range(min(y1, y2), max(y1, y2)):
            if row not in spans:
                spans[row] = (float("inf"), float("-inf"))
            spans[row] = (min(spans[row][0], x1), max(spans[row][1], x1 - 1))

    return spans

def band_sweep(spans, anchor_y, cutter) -> tuple[int, int] | None:
    bounds = (float("inf"), float("-inf"))
    for row in range(anchor_y + cutter.bottom, anchor_y + cutter.top + 1):
        if row not in spans:
            continue
        bounds = (min(bounds[0], spans[row][0]), max(bounds[1], spans[row][1]))

    start = bounds[0] - cutter.left
    end = bounds[1] - cutter.right

    if start > end:
        return (start, start) if bounds[0] != float('inf') and bounds[1] != float('-inf') else None
    return (start, end)

def solve(instance: CGSHOP2027Instance) -> CGSHOP2027Solution:
    boundary = instance.region_to_cover.outer_boundary
    lawn = Rect.enclosing(boundary.x, boundary.y)
    cutter = compute_rect_cutter(instance.cutter, instance.cutter_center)

    strip_count = max(ceil(lawn.height / cutter.height), instance.number_of_cutters)
    anchor_rows = [lawn.top - cutter.top - i * cutter.height for i in range(strip_count)]

    spans = row_spans(boundary)
    bands = []
    for row in anchor_rows:
        sweep = band_sweep(spans, row, cutter)
        if sweep is None:
            continue
        bands.append((row, sweep[0], sweep[1]))

    tours = []
    for block in divide(instance.number_of_cutters, bands):
        tours.append(tour(list(block)))

    return CGSHOP2027Solution(
        instance_uid=instance.instance_uid,
        tours=tours,
        meta={"algorithm": "scanline"},
    )


def tour(bands: list[tuple[int, int, int]]) -> CutterTour:
    if len(bands) == 0:
        return CutterTour(x=[0], y=[0])

    points = []
    x_in = bands[0][1] 
    for i, (y, x_start, x_end) in enumerate(bands):
        going_right = i % 2 == 0
        if i + 1 < len(bands):
            _, next_start, next_end = bands[i + 1]
            x_out = max(x_end, next_end) if going_right else min(x_start, next_start)
        else:
            x_out = x_end if going_right else x_start
        points.append((x_in, y))
        points.append((x_out, y))
        x_in = x_out
    points.append((points[0][0], points[-1][1]))

    points = list(unique_justseen(points))
    return CutterTour(x=[x for x, _ in points], y=[y for _, y in points])
