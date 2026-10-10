## Description

This solver assumes a rectangular cutter and trims each horizontal strip to the part of the lawn it needs to cover, with each cutter snaking through its strips of the lawn.

## Building and Running

To run on all example instances.

```
uv run main.py output_solutions
```

## Evaluation

```
uv run --project ../../utils \
  ../../utils/eval-solver.py \
  ../../examples/test_instances1 \
  output_solutions
```

