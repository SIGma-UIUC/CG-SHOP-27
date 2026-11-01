# Exact single-cutter solver

This solver uses CP-SAT to find a minimum-length closed tour for one cutter.
The instance must specify exactly one cutter. Region and cutter polygons are
rasterized to grid cells; the cutter does not need to be rectangular. The
solver accepts at most 200 distinct cutter-center positions that cover region
cells. There is no separate region-cell limit, but this also means a region
can contain at most 200 rasterized cells: each region cell contributes a
distinct covering position for any fixed cutter-cell offset. The cutter shape
may cause the 200-position limit to be reached with fewer region cells.

The movement graph also includes transit positions in the integer bounding
box, so the tour can travel between mowing positions without cutting. The
model uses a closed-walk bound of twice the number of movement-grid edges and
no heuristic starting route or solution hint. CP-SAT has a fixed 50-second
time limit. It returns a feasible solution if one is found before the limit;
optimality is not guaranteed. The output metadata reports the best objective
bound, solve time, and whether optimality was proved.

Run it from this directory:

```sh
uv run main.py input.instance.json output.solution.json
```

The output is a standard CG:SHOP solution JSON. Its `meta` object includes the
CP-SAT status and whether optimality was proved. Instances with more than 200
distinct covering cutter-center positions are rejected. If CP-SAT finds no
feasible tour within the time limit, the command exits with an error instead
of writing a solution file.

Designed baseline instances and their exact solutions are in
`examples/exact-small`.

Run the focused tests with:

```sh
uv run python -m unittest
```

The testcase generator can create larger cases for experiments. Add
`--rectangular-region` and `--rectangular-cutter` to generate an axis-aligned
rectangular lawn and robot with the requested cell counts. For example:

```sh
uv run python generate_testcases.py examples/generated-rectangles \
  --seed 2030 \
  --region-cells 28 30 32 \
  --cutter-cells 7 9 11 \
  --rectangular-region \
  --rectangular-cutter
```

Omit `--rectangular-region` to generate irregular connected lawns while keeping
the robot rectangular:

```sh
uv run python generate_testcases.py examples/generated-irregular-rectangles \
  --seed 3070 \
  --region-cells 28 30 32 \
  --cutter-cells 8 10 12 \
  --rectangular-cutter
```
