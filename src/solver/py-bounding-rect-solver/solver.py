from math import ceil
from typing import NamedTuple, Self

from more_itertools import divide, flatten, unique_justseen

from cgshop2027_pyutils.schemas import (
    CGSHOP2027Instance,
    CGSHOP2027Solution,
    CutterTour,
)

class Rectangle(NamedTuple):
    """
    A rectangle object described by the distance of the left, bottom, right, top edges from the center
    """
    left: int
    bottom: int
    right: int
    top: int

    def x_span(self, dx: int = 0) -> tuple[int, int]:
        """Returns the left and right edge of the rightangle offsetted by dx"""
        return self.left + dx, self.right + dx

    def y_span(self, dy: int = 0) -> tuple[int, int]:
        """Returns the top and bottom edge of the rectangle offsetted by dy"""
        return self.bottom + dy, self.top + dy

    @property
    def height(self) -> int:
        """Height of the rectangle"""
        return self.top - self.bottom + 1

    @property
    def width(self) -> int:
        """Width of the rectangle"""
        return self.right - self.left + 1

    @classmethod
    def enclosing(
        cls,
        xs: list[int],
        ys: list[int],
        offset=(0, 0)
    ) -> Self:
        """This computes a rectangular shape that covers xs and ys by aligning the four sides
        of the rectangle: left side, right side, bottom side and up side to the minimum of the xs,
        the maximum of the xs, the minimum of the ys, the maximum of the ys respectively shifted 
        by the relative center of the shape.

        A cutter given by the instance desrcibes its vertices position given a center
        
        "cutter": {
            "x": [1, 0, 0, 1, 1, 3, 3, 4, 4, 3, 3, 1],
            "y": [3, 3, 1, 1, 0, 0, 1, 1, 3, 3, 4, 4]
        },
        "cutter_center": [2, 2],

        When we call Rectangle.enclosing(cutter), we consider the rectangle that covers the shape centered 
        at (0,0) instead of (2,2) in this example.

        Args:
            xs: the list of x coordinates
            ys: the list of y coordinates
            offset: the relative origin of the x and y coordinates
            
        Returns:
            A rectangle object that covers xs and ys centered at the absolute origin
        """
        offset_x, offset_y = offset
        return cls(
            min(xs) - offset_x,
            min(ys) - offset_y,
            max(xs) - 1 - offset_x,
            max(ys) - 1 - offset_y,
        )

def solve(instance: CGSHOP2027Instance) -> CGSHOP2027Solution:
    """Solves an instance of the problem by solving instead an auxillary rectangular
    cover of the instance. Any solution to that auxillary rectangular cover
    necessarily covers the instance itself.

    Args:
        instance: polyomino lawn with holes possibly.
    Returns:
        A solution to an rectangular cover of instance.
    """
    number_of_cutters = instance.number_of_cutters
    boundary = instance.region_to_cover.outer_boundary
    lawn = Rectangle.enclosing(boundary.x, boundary.y)
    cutter = Rectangle.enclosing(
        instance.cutter.x, instance.cutter.y, instance.cutter_center
    )

    x_start, x_end = lawn.left - cutter.right, lawn.right - cutter.left
    y_start, y_end = lawn.top - cutter.bottom, lawn.bottom - cutter.top

    rows_strip_count = max(
        ceil(lawn.height / cutter.height), number_of_cutters
    )
    columns_strip_count = max(
        ceil(lawn.width / cutter.width), number_of_cutters
    )

    anchor_rows = [
        lawn.top - cutter.top - i * cutter.height for i in range(rows_strip_count)
    ]
    anchor_columns = [
        lawn.left - cutter.left + i * cutter.width for i in range(columns_strip_count)
    ]

    tours_vertical = []
    for block in divide(number_of_cutters, anchor_columns):
        tours_vertical.append(_tour_vertical(list(block), y_start, y_end))

    tours_horizontal = []
    for block in divide(number_of_cutters, anchor_rows):
        tours_horizontal.append(_tour_horizontal(list(block), x_start, x_end))

    def best_tour(tours_horizontal, tours_vertical):
        longest_horizontal_tour = max(tours_horizontal, key=lambda tour: tour.length).length
        longest_vertical_tour = max(tours_vertical, key=lambda tour: tour.length).length
        return tours_horizontal if longest_horizontal_tour < longest_vertical_tour else tours_vertical

    return CGSHOP2027Solution(
        instance_uid=instance.instance_uid,
        tours=best_tour(tours_horizontal, tours_vertical),
        meta={"algorithm": "bounding-rect strips"},
    )
    # This the largest number of rows and columns that any cutter will be assigned to.

def _tour_horizontal(
        anchor_rows: list[int],
        x_start: int,
        x_end: int
    ) -> CutterTour:
    """It computes a tour of the anchor_rows in a zig-zag manner. For example, if
    anchor row has size 5 and the difference between x_start and x_end is 5, then our tour traverses the rows
    in the following manner
        1/12***2/11
        4***3
        5***6
        8***7
        9***10
    where the number indicates the ith check point. We assume for simplicity, 1 * 1 mower.
    We return to the start of the first row from 10 via 11 and 12.

    Args:
        anchor_rows: the rows we need to traverse given that they are consecutive rows
        x_start: the horizontal start point of our traversal
        x_end: the horizontal end point of our traversal
    Returns:
        A CutterTour object that specifies our tour in the required format.
    """
    check_points = []

    for i, y in enumerate(anchor_rows):
        check_points.extend(
            [(x_start, y), (x_end, y)] if _is_even(i) else [(x_end, y), (x_start, y)]
        )

    first_x, first_y = check_points[0]
    last_x, last_y = check_points[-1]

    if last_x != first_x and last_y != first_y:
        check_points.append((last_x, first_y))

    return CutterTour(x=[x for x, _ in check_points], y=[y for _, y in check_points])

def _tour_vertical(
        anchor_cols: list[int],
        y_start: int,
        y_end: int
    ) -> CutterTour:
    """The same as tour_horizontal except that we sweep columns"""
    check_points = []

    for i, x in enumerate(anchor_cols):
        check_points.extend(
            [(x, y_start), (x, y_end)] if _is_even(i) else [(x, y_end), (x, y_start)]
        )

    first_x, first_y = check_points[0]
    last_x, last_y = check_points[-1]

    if last_x != first_x and last_y != first_y:
        check_points.append((first_x, last_y))

    return CutterTour(x=[x for x, _ in check_points], y=[y for _, y in check_points])

def _is_even(number: int):
    return (number & 1) == 0
