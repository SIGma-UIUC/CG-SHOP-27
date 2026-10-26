#!/usr/bin/env bash
# Workflow-only glue for solver-benchmark.yml. Run from the repository root.
set -euo pipefail

candidate_python='candidate/src/utils/.venv/bin/python'

benchmark_python() {
  if [ "${GITHUB_ACTIONS:-false}" = true ]; then
    # Give BenchExec its own delegated cgroup while keeping execution unprivileged.
    sudo systemd-run --quiet --wait --pipe --collect \
      --property="User=$(id -un)" --property="Group=$(id -gn)" --property=Delegate=yes \
      --working-directory="$PWD" --setenv="PATH=$PATH" \
      "$(realpath "$candidate_python")" "$@"
  else
    "$candidate_python" "$@"
  fi
}

fetch_inputs() {
  local args=()
  [ "${INCLUDE_LARGE:-false}" = true ] && args+=(--large)
  "$candidate_python" candidate/src/utils/benchmark-instances.py \
    merged/src/examples/test_instances1 --sample 15 "${args[@]}" --output benchmark-inputs
}

cache_key() {
  local manifest=$1 prefix=$2
  sha256sum "$manifest" \
    "$prefix/src/utils/benchmark-instances.py" \
    "$prefix/src/utils/benchmark-run.py" \
    "$prefix/src/utils/benchmark-report.py" \
    "$prefix/src/utils/benchmark-baseline.py" \
    "$prefix/src/utils/pyproject.toml" \
    "$prefix/src/utils/uv.lock" \
    "$prefix/.github/scripts/solver-benchmark.sh" \
    "$prefix/.github/actions/solver-benchmark/action.yml" \
    "$prefix/.github/workflows/solver-benchmark.yml" \
    | cut -d' ' -f1 | sha256sum | cut -d' ' -f1 > cache-key.txt
}

find_changed() {
  : > changed.txt
  : > removed.txt
  if [ "$GITHUB_EVENT_NAME" = pull_request ]; then
    declare -A names=()
    for root in candidate/src/solver merged/src/solver; do
      for folder in "$root"/*; do [ -d "$folder" ] && names["$(basename "$folder")"]=1; done
    done
    for name in "${!names[@]}"; do
      if [ ! -d "candidate/src/solver/$name" ]; then
        echo "$name" >> removed.txt
      elif [ ! -d "merged/src/solver/$name" ] || ! diff -qr --exclude=.venv "candidate/src/solver/$name" "merged/src/solver/$name" >/dev/null; then
        echo "$name" >> changed.txt
      fi
    done
  else
    for folder in candidate/src/solver/*; do
      [ -f "$folder/main.py" ] && [ -f "$folder/pyproject.toml" ] && basename "$folder" >> changed.txt
    done
  fi
  sort -u -o changed.txt changed.txt
  sort -u -o removed.txt removed.txt
  echo "changed=$(paste -sd, changed.txt)" >> "$GITHUB_OUTPUT"
  echo "removed=$(paste -sd, removed.txt)" >> "$GITHUB_OUTPUT"
}

select_baseline() {
  local args=()
  while IFS= read -r name; do [ -n "$name" ] && args+=(--solver "$name"); done < <(cat changed.txt removed.txt)
  "$candidate_python" candidate/src/utils/benchmark-baseline.py select \
    --baseline baseline.json --sample benchmark-inputs/manifest.json --solver-root merged/src/solver \
    "${args[@]}" --cache-key "$(cat cache-key.txt)" --output baseline-selection.json
  jq '.rows' baseline-selection.json > prior-results.json
  jq -r '.missing[]' baseline-selection.json | while IFS= read -r name; do
    if [ -d "merged/src/solver/$name" ]; then
      echo "$name"
    fi
  done > missing.txt
  echo "has-missing=$([ -s missing.txt ] && echo true || echo false)" >> "$GITHUB_OUTPUT"
}

install_solvers() {
  declare -A projects=()
  while IFS= read -r name; do [ -n "$name" ] && projects["candidate/src/solver/$name"]=1; done < changed.txt
  if [ "$GITHUB_EVENT_NAME" = pull_request ]; then
    while IFS= read -r name; do [ -n "$name" ] && projects["merged/src/solver/$name"]=1; done < missing.txt
  fi
  for project in "${!projects[@]}"; do
    [ -f "$project/main.py" ] && [ -f "$project/pyproject.toml" ] && uv sync --frozen --project "$project"
  done
}

run_solvers() {
  local label=$1 root=$2 names=$3 output=$4
  local args=()
  while IFS= read -r name; do [ -n "$name" ] && args+=(--solver "$name"); done < "$names"
  benchmark_python candidate/src/utils/benchmark-run.py benchmark-inputs/instances \
    --solver-root "$label=$root" "${args[@]}" --timeout 30 --animate --output "$output"
}

write_report() {
  local dumps=${1:-}
  local prior=()
  [ -f prior-results.json ] && prior=(--prior-results prior-results.json)
  local args=(--manifest benchmark-inputs/manifest.json "${prior[@]}" --output benchmark-results)
  [ -n "$dumps" ] && args=(--dumps "$dumps" "${args[@]}")
  "$candidate_python" candidate/src/utils/benchmark-report.py "${args[@]}"
}

publish_cache() {
  uv sync --frozen --project src/utils
  cache_key benchmark-results/sample.json .
  src/utils/.venv/bin/python src/utils/benchmark-baseline.py write \
    --results benchmark-results/results.json --sample benchmark-results/sample.json \
    --solver-root src/solver --cache-key "$(cat cache-key.txt)" --output baseline.json
}

case "${1:-}" in
  check-runner) benchmark_python candidate/src/utils/benchmark-smoke.py ;;
  fetch-inputs) fetch_inputs ;;
  cache-key-pr) cache_key benchmark-inputs/manifest.json candidate ;;
  find-changed) find_changed ;;
  select-baseline) select_baseline ;;
  install-solvers) install_solvers ;;
  run-merged) run_solvers merged merged/src/solver missing.txt merged-dumps ;;
  report-merged)
    "$candidate_python" candidate/src/utils/benchmark-report.py --dumps merged-dumps \
      --prior-results prior-results.json \
      --manifest benchmark-inputs/manifest.json --output merged-results
    cp merged-results/results.json prior-results.json
    ;;
  run-proposed) run_solvers candidate candidate/src/solver changed.txt benchmark-dumps ;;
  report-proposed) write_report benchmark-dumps ;;
  report-empty) write_report ;;
  publish-cache) publish_cache ;;
  *) echo "usage: $0 {check-runner|fetch-inputs|cache-key-pr|find-changed|select-baseline|install-solvers|run-merged|report-merged|run-proposed|report-proposed|report-empty|publish-cache}" >&2; exit 2 ;;
esac
