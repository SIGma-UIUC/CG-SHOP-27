# Exact oracle for one rectangular cutter

A readable CP-SAT solver for **one axis-aligned rectangular cutter on a
rectangular lawn without holes**. This implements the task described in
[Problem_Description.md](Problem_Description.md), restricted to the rectangular
scope. The implementation plan is in [PLAN.md](PLAN.md).

The oracle minimizes the length of one closed rectilinear trajectory. Turning
points are integers, there is no prescribed start, retracing is allowed, and
neither the cutter nor its center is constrained to stay inside the lawn.
A stationary cutter is a valid zero-length solution. Nonrectangular shapes,
holes, and multiple cutters are rejected, never approximated by bounding boxes.

## Run

From this directory, with Python 3.14+ and `uv`:

```sh
uv sync --locked
uv run main.py
uv run main.py output_solutions --instances /path/to/tiny.instance.json
uv run main.py output_solutions --instances /path/to/instances --time-limit 50
uv run pytest -q
```

By default, the solver reads every `*.instance.json` in `examples/instances/`
and writes matching solutions plus `report.json` to `examples/solutions/`.
Both defaults are relative to this script, so they work from any working directory.
An optional output directory and `--instances` override these defaults. Dependencies are locked,
including the competition utility revision. The runtime dependencies are OR-Tools
and `cgshop2027-pyutils`; the development group adds pytest and the existing strip
solver's `more-itertools` dependency for baseline comparisons.

Each feasible result is checked with the competition verifier, then written as
`<input-stem>.solution.json`. Diagnostics are printed as JSON and saved together
in `report.json`, including rejected inputs and runs with no solution. The CLI
returns 1 if any input is rejected or has no incumbent, and 0 otherwise. A
FEASIBLE result is usable but is **not** a proved optimum. Rerunning into the same
output directory replaces results for the selected inputs and removes their
stale solution files if the new run produces no solution.

Defaults are **20 candidate center positions**, **36 required unit lawn cells**,
and **50 seconds of CP-SAT search per instance**. Geometry preparation and output
verification are outside that backend time limit. Use `--max-positions` and
`--max-cells` to override the size guards explicitly. The complete grid is used;
positions are never sampled to fit the limit. Large overrides may be expensive.

For a lawn of width W and height H and a cutter of width w and height h, the
candidate count is `(W + w - 1) * (H + h - 1)`. Thus a larger cutter can exceed the
position limit even on a small lawn. The repository's general example instances
are mostly outside this oracle's intended scope; the bundled examples are tiny.

## Python API and result meaning

```python
from cgshop2027_pyutils.io import read_instance
from solver import solve

result = solve(read_instance("examples/instances/square.instance.json"))
print(result.report())
if result.solution is not None:
    print(result.solution.model_dump_json())
```

`solve()` returns a `SolveResult`, rather than returning only a solution, so a
failed or interrupted search can still be reported. Invalid/unsupported input
raises `ValueError`. Diagnostics are also stored in each solution's `meta`:

| Field | Meaning |
| --- | --- |
| `status` | CP-SAT's OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN, or MODEL_INVALID |
| `proved_optimal` | True only when the backend returns OPTIMAL |
| `objective` | Incumbent closed-tour length, or null when none was found |
| `best_bound` | Backend lower bound, including for UNKNOWN; null for INFEASIBLE/MODEL_INVALID |
| `wall_time_seconds` | Backend-reported elapsed search time |
| `candidate_positions`, `required_cells` | Grid and coverage sizes |

The CLI additionally uses UNSUPPORTED for valid instances outside its geometry
or size limits, and REJECTED for invalid inputs or file errors. It prints a batch
summary including how many solutions were actually generated. UNKNOWN does not imply
infeasibility. No tour is extracted for UNKNOWN, INFEASIBLE, or MODEL_INVALID.
A single search worker and fixed random seed improve reproducibility, although
wall-clock timeouts can still produce different incumbents on different hosts.

## Why this is exact

### Coverage and the finite grid

A lawn cell is the entire closed unit square with a given lower-left integer
corner, not merely a sample point. Subtracting `cutter_center` from the cutter's
polygon coordinates gives its footprint relative to every candidate center.

Write the lawn bounds as `[L,R] x [B,T]` and the relative cutter bounds as
`[a,b] x [c,d]`. The candidate center coordinates are every integer point in

```text
[L - b + 1, R - a - 1] x [B - d + 1, T - c - 1].
```

These are all integer placements with positive-area lawn overlap, including
placements outside the lawn. For integer rectilinear trajectories, subdivide
all movements into unit steps. A rectangle has integer width and height at
least one, so the union of its footprints at the two ends of a unit step equals
the entire continuous swept rectangle. Endpoint cell coverage therefore captures
all coverage along a movement, including cells between original turning points.

Every integer placement that covers a lawn cell is in the candidate box.
Coordinatewise clamping an arbitrary closed tour to this box fixes every such
placement, preserves rectilinearity and integer coordinates, and cannot increase
Manhattan length. Hence some global optimum lies in this finite grid. The size
limits reject instances; they do not weaken the optimum claimed for accepted
instances.

### Closed walk model

`solver.py` separates geometry (`build_grid`), modeling (`build_model`), tour
extraction (`extract_tour`), and search/reporting (`solve`). The model has:

- A binary visit variable per center position, and coverage of every lawn cell
  by at least one visited footprint.
- A binary traversal variable for each directed unit-neighbor edge. Both
  directions may be selected, allowing out-and-back movement.
- Equal incoming and outgoing traversal counts at every vertex.
- One selected root and a flow from that root that delivers one unit to each
  visited vertex. This rules out disconnected cycles and isolated coverage.
- An objective equal to the number of selected directed edges, each of length 1.

The root may be any position covering the first lawn cell: every feasible tour
visits one, and a closed tour can start there without changing its geometry.
Only the root can be visited without an incident edge, which permits a stationary
cutter exactly when its footprint covers the entire lawn.

Binary directed edges do not exclude an optimum. View any closed walk as a
connected undirected Eulerian multigraph. If an edge appears at least three times,
removing two copies preserves even degrees and connectivity, while shortening
the walk. An optimum therefore uses each undirected edge at most twice. Orient
each doubled edge once in each direction. The remaining single edges have even
degrees and can be oriented along Eulerian circuits. This gives a balanced,
connected directed graph using each direction at most once. Conversely, every
model solution has an Eulerian circuit, recovered by Hierholzer's algorithm.

Thus OPTIMAL certifies the global optimum for the supported integer-turning-point
problem, not just a tour restricted to distinct positions. For one cutter the
problem statement identifies this integer restriction as without loss of
generality. With one cutter, the longest-tour objective is simply its length.

## Validation

Tests check:

- Analytic optima: stationary cutters, strips requiring retracing, rectangular
  cycles, odd-area unit-cutter lawns, and a 20-position case.
- All 36 combinations of 1–3 by 1–3 lawns and 1–2 by 1–2 cutters against independent
  exhaustive BFS over position/coverage states. The BFS allows unrestricted
  revisits and uses geometric footprint containment for its coverage masks.
- Three comparisons with `../py-bounding-rect-solver/solver.py`, checking both
  feasibility and that the oracle is no worse than the strip heuristic.
- The official competition verifier for every returned baseline/test tour.
- Translations, cutter-center offsets, exterior candidates, collinear rectangle
  vertices, unsupported inputs, limit overrides, timeout reporting, and CLI output.

The supplied [CP-SAT PDF](CP-SAT%20Solver%20_%20OR-Tools%20_%20Google%20for%20Developers.pdf)
provides the integer modeling API and backend status semantics used here.
