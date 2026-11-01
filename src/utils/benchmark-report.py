"""Build portable benchmark report artifacts from measurements."""

import argparse
import json
import math
from pathlib import Path
import shutil


PUBLIC_FIELDS = {
    'solver', 'instance', 'status', 'efficiency', 'max_len', 'time_s',
    'memory_mib', 'swept_area', 'per_tour_swept_areas', 'tour_lengths',
    'cutters', 'area', 'animation', 'animation_status', 'errors',
}


def public_row(row):
    if not isinstance(row, dict):
        raise ValueError('Every raw result must be an object')
    public = {key: value for key, value in row.items() if key in PUBLIC_FIELDS}
    for key in ('solver', 'instance', 'status'):
        if not isinstance(public.get(key), str):
            raise ValueError(f'Missing or invalid {key!r} in a raw result')
    for key in ('efficiency', 'max_len', 'time_s', 'memory_mib', 'swept_area', 'area'):
        if key in public and public[key] is not None and (not isinstance(public[key], (int, float)) or not math.isfinite(public[key])):
            public[key] = None
    animation = public.get('animation')
    if animation is not None and (not isinstance(animation, str) or not animation.startswith('run-') or not animation.endswith('/animation.gif')):
        public.pop('animation', None)
    return public


def report(rows, output):
    best = {}
    for row in rows:
        if row['status'] == 'valid' and isinstance(row.get('max_len'), (int, float)):
            best[row['instance']] = min(best.get(row['instance'], math.inf), row['max_len'])
    leaderboard = []
    for solver in sorted({row['solver'] for row in rows}):
        group = [row for row in rows if row['solver'] == solver]
        valid = [row for row in group if row['status'] == 'valid' and isinstance(row.get('max_len'), (int, float))]
        score = sum(1 if row['max_len'] == 0 else best[row['instance']] / row['max_len'] for row in valid) / len(group)
        leaderboard.append((len(valid), score, solver, len(group)))
    (output / 'leaderboard.json').write_text(json.dumps(sorted(leaderboard, key=lambda r: (-r[0], -r[1], r[2])), indent=2) + '\n')
    lines = ['| Solver | Instance (UID) | Status | Efficiency | Max len | Time (s) | Memory (MiB) | Animation |', '|---|---|---:|---:|---:|---:|---:|---|']
    for row in rows:
        number = lambda key: '-' if row.get(key) is None else f"{row[key]:.3f}"
        lines.append(f"| {row['solver']} | {row['instance']} | {row['status']} | {number('efficiency')} | {number('max_len')} | {number('time_s')} | {number('memory_mib')} | {'yes' if row.get('animation') else '-'} |")
    (output / 'report.md').write_text('\n'.join(lines) + '\n')


def load_rows(dumps, prior_results):
    rows = []
    if prior_results:
        rows.extend(json.loads(prior_results.read_text()))
    if dumps:
        rows.extend(json.loads((dumps.resolve() / 'raw-results.json').read_text()))
    return [public_row(row) for row in rows]


def copy_animations(rows, dumps, output):
    dump_root = dumps.resolve() if dumps else None
    for row in rows:
        animation = row.get('animation')
        if not animation or dump_root is None:
            row.pop('animation', None)
            continue
        source, destination = dump_root / animation, output / animation
        if not source.is_file() or not source.resolve().is_relative_to(dump_root):
            row.pop('animation', None)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dumps', type=Path, help='Directory written by benchmark-run.py')
    parser.add_argument('--prior-results', type=Path, help='Previously reported rows to retain')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = load_rows(args.dumps, args.prior_results)
    copy_animations(rows, args.dumps, output)
    (output / 'results.json').write_text(json.dumps(rows, indent=2, allow_nan=False) + '\n')
    shutil.copyfile(args.manifest, output / 'sample.json')
    report(rows, output)


if __name__ == '__main__':
    main()
