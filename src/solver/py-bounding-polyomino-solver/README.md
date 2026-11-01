## Description

This solver approximates the lawn as a rectangle via the bounding box.
It generates a solution with each robot scanning horizontal strips of the lawn.

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

