from collections import Counter, defaultdict
from collections.abc import Iterator
from typing import NamedTuple, Self

from cgshop2027_pyutils.schemas import (
    CGSHOP2027Instance,
    CGSHOP2027Solution,
    CutterTour,
)

class Rec(NamedTuple):
    """
    A rectangle object described by the distance of the left, bottom, right, top edges from the center
    """
    left: int
    bottom: int
    right: int
    top: int

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

def rotate_2d_points(points, angle_degrees, center=(0, 0)):
    """Rotate grid points by quarter turns without floating-point rounding."""
    if angle_degrees % 90 != 0:
        raise ValueError("Grid rotations must be multiples of 90 degrees")
    turns = int(angle_degrees // 90) % 4
    center_x, center_y = center
    rotated = []
    for x, y in points:
        x, y = x - center_x, y - center_y
        for _ in range(turns):
            x, y = -y, x
        rotated.append((x + center_x, y + center_y))
    return rotated

def single_lawn_mower_solve(instance: CGSHOP2027Instance) -> CGSHOP2027Solution:
    """Solves an instance of the problem by solving instead a covering polyomino region
    with no inner holes. 

    Args:
        instance: polyomino lawn with holes possibly.
    Returns:
        A solution to an polyomino cover of instance.
    """
    number_of_cutters = instance.number_of_cutters

    boundary = instance.region_to_cover.outer_boundary
    vertices = list(zip(boundary.x, boundary.y, strict=True))
    rotated_vertices = rotate_2d_points(vertices, 90)

    cutter = Rec.enclosing(
        instance.cutter.x, instance.cutter.y, instance.cutter_center
    )
    # Bounds describe cells, so [bottom, top + 1] becomes [-top - 1, -bottom].
    rotated_cutter = Rec(
        -cutter.top - 1, cutter.left, -cutter.bottom - 1, cutter.right
    )

    def solve(vertices, cutter):
        check_points: list[tuple[int, int]] = []
        
        def append_point(x: int, y: int) -> None:
            if not check_points or check_points[-1] != (x, y):
                check_points.append((x, y))
    
        for x, bottom, top in _column_bounds(vertices):
            center_x = x - cutter.left
            high = top - cutter.bottom
            low = bottom - cutter.top
            start_y, end_y = (high, low) if x % 2 == 0 else (low, high)
    
            if check_points:
                # Make a step forward, this is useful if the start of the next 
                # check point is not the end of the current checkpoint
                # if they are the same then this step does nothing, otherwise we
                # add a intermediate step
    
                append_point(center_x, check_points[-1][1])
            append_point(center_x, start_y)
            append_point(center_x, end_y)
    
        first_x, first_y = check_points[0]
        last_x, last_y = check_points[-1]
    
        if last_x != first_x and last_y != first_y:
            append_point(first_x, last_y)
    
        if len(check_points) > 1 and check_points[-1] == check_points[0]:
            check_points.pop()
    
        tours = [
            CutterTour(
                x=[x for x, _ in check_points],
                y=[y for _, y in check_points],
            )
        ]
    
        tours.extend(
            CutterTour(x=[first_x], y=[first_y])
            for _ in range(instance.number_of_cutters - 1)
        )

        return check_points

    tours_horizontal_check_points = rotate_2d_points(
        solve(rotated_vertices, rotated_cutter), -90
    )
    tours_vertical_check_points = solve(vertices, cutter)

    vertical_tours = _form_tours_from_checkpoints(tours_vertical_check_points, number_of_cutters)

    horizontal_tours = _form_tours_from_checkpoints(tours_horizontal_check_points, number_of_cutters)


    return CGSHOP2027Solution(
        instance_uid=instance.instance_uid,
        tours=_best_tour(horizontal_tours, vertical_tours),
        meta={"algorithm": "bounding-polyomino zig-zag"},
    )


def _form_tours_from_checkpoints(check_points, number_of_cutters):
    """Forms tours from the check point
    
    Args:
        check_points: The vertices/checkpoints of a cutter tour
        number_of_cutters: The number of cutters allowed in the instance
    
    Return:
        A list of cutter tour
    
    """
    tours = [
        CutterTour(
            x=[x for x, _ in check_points],
            y=[y for _, y in check_points],
        )
    ]
    tours.extend(
        CutterTour(x=[0], y=[0])
        for _ in range(number_of_cutters - 1)
    )
    return tours

def _best_tour(tours_horizontal, tours_vertical):
    """Returns the best tour
    
    Args:
        tours_horizontal: A horizontal tour of the region
        tours_vertical: A vertical tour of the region
    Returns:
        tours_horizontal if it is better than tours_vertical else tours_vertical
    
    """
    longest_horizontal_tour = max(tours_horizontal, key=lambda tour: tour.length).length
    longest_vertical_tour = max(tours_vertical, key=lambda tour: tour.length).length

    print(longest_horizontal_tour, longest_vertical_tour)
    return tours_horizontal if longest_horizontal_tour < longest_vertical_tour else tours_vertical

def _column_bounds(vertices) -> Iterator[tuple[int, int, int]]:
    """Yield (x, bottom, top) cell bounds, filling holes and vertical gaps.

    Args:
        xs: the x coordinates of the vertices of the outer boundary
        ys: the y coordinates of the vertices of the outer boundary
    Returns:
        An iterator iterating over all (x, bottom, top) for all possible x in the lawn
    """
    # It tracks the changes at a given x coordinate
    # events[2] = [(6, -1), (4, +1)]
    # means: “At x = 2, the edge at height 6 ends, and an edge at height 4 begins.”
    events: dict[int, list[tuple[int, int]]] = defaultdict(list)

    # This creates a list of pairs where every element is a pair ((x1,y1), (x2,y2)) and 
    # (x2,y2) is the immediate successor to (x1, y1)
    for (x1, y1), (x2, y2) in zip(vertices, vertices[1:] + vertices[:1]):
        # If we have two vertices that are at the same y but at different
        # x coordinates, we append (y1, 1) to events[left] to indicate
        # the start of a horizontal bounday and then append (y2, -1) to 
        # indcate the end of a horizontal boundary
        if y1 == y2 and x1 != x2:
            left, right = sorted((x1, x2))
            events[left].append((y1, 1))
            events[right].append((y1, -1))

    # Keeps track of the currently horizontal boundaries in a given interval
    # this is useful for generating our top and bottom bounds
    active: Counter[int] = Counter()
    event_xs = sorted(events)

    # Iterate through every interval.
    # Track every horizontal boundaries
    for left, right in zip(event_xs, event_xs[1:]):
        # for the ys in events[left]
        for y, change in sorted(events[left]):
            active[y] += change
            # if a horizontal boundary no longer continues
            # remove it
            if active[y] == 0:
                del active[y]

        # return the lowest and highest of the active horizontal boundaries
        # as the top and bottom.
        if active:
            bottom, top = min(active), max(active) - 1
            for x in range(left, right):
                yield x, bottom, top
