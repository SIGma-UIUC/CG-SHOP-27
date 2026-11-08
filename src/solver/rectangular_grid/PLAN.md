# Implementation plan

1. Read the task, problem statement, supplied CP-SAT PDF, existing strip solver,
   and installed competition schemas. Confirm the rectangular scope.
2. Validate one cutter, a rectangular cutter, and a rectangular lawn without
   holes. Respect cutter-center offsets. Reject oversized inputs before building
   the grid (defaults: 20 positions, 36 unit lawn cells).
3. Build the complete finite integer grid of positions whose footprints overlap
   a lawn cell. Prove that clamping an arbitrary tour to this box preserves
   coverage and cannot increase length. Represent continuous sweeps exactly by
   unit-step endpoint coverage.
4. Minimize a connected Eulerian walk using binary directed unit edges,
   balanced degrees, selectable root, and connectivity flow. Include stationary
   cutters and retracing. Explain why these edge bounds preserve an optimum.
5. Extract a tour in the competition format. Report CP-SAT status, optimality,
   objective, lower bound, time, and model size, including runs with no incumbent.
   Default to a 50-second backend time limit.
6. Add a single-file/directory CLI, reproducible dependency configuration, usage
   documentation, and tiny sample instances.
7. Compare with analytic optima, independent exhaustive walk search, and the
   existing bounding-rectangle baseline. Check returned tours with the official
   verifier. Exercise offsets, exterior movement, rejected inputs, limits, and
   timeout reporting.

Scope assumption: both cutter and lawn are rectangles. General polyominoes and
multiple cutters are rejected rather than silently replaced by bounding boxes.

## Completion

The user confirmed the rectangular cutter/rectangular lawn scope. All seven
steps are implemented. Validation completed with 67 passing tests, including
36 independent exhaustive comparisons and three existing-strip-solver
comparisons. The CLI also solved and officially verified all four bundled
examples, proving lengths 0 (stationary), 6 (strip), 4 (square with 2x2 cutter),
and 10 (odd square with unit cutter). Tests explicitly check disconnected-cycle
rejection, an exterior stationary center, UNKNOWN without an incumbent, and
FEASIBLE status handling without an optimality claim.
