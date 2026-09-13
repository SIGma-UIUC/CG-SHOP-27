"""Benchmark solver directory CLIs, or validate an existing solution directory."""

import argparse
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import psutil


def area(data):
    def polygon(p):
        pts = list(zip(p['x'], p['y']))
        return abs(sum(x * v - u * y for (x, y), (u, v) in zip(pts, pts[1:] + pts[:1]))) / 2
    region = data['region_to_cover']
    return polygon(region['outer_boundary']) - sum(polygon(p) for p in region.get('inner_boundaries', []))


def sample(paths, count):
    """Deterministic size-stratified sample, preferring unseen instance families."""
    ordered = sorted(paths, key=lambda p: (area(json.loads(p.read_text())), p.name))
    if count == 0 or count >= len(ordered):
        return ordered
    selected, families = [], set()
    for i in range(count):
        lo, hi = i * len(ordered) // count, (i + 1) * len(ordered) // count
        bucket = ordered[lo:hi]
        p = next((p for p in bucket if p.name.split('_')[0] not in families), bucket[len(bucket) // 2])
        selected.append(p)
        families.add(p.name.split('_')[0])
    return selected


def run(command, timeout, log, cwd=None):
    """Bound wall time and sample total process-tree RSS every 20 ms."""
    start, peak, tracked = time.perf_counter(), 0, {}
    with log.open('wb') as stream:
        proc = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=os.name != 'nt')
        parent = psutil.Process(proc.pid)
        expired = False
        try:
            while True:
                try:
                    for child in [parent, *parent.children(recursive=True)]:
                        tracked[child.pid] = child
                except psutil.Error:
                    pass
                rss = 0
                for child in tracked.values():
                    try:
                        rss += child.memory_info().rss
                    except psutil.Error:
                        pass
                peak = max(peak, rss)
                if proc.poll() is not None:
                    break
                if time.perf_counter() - start >= timeout:
                    expired = True
                    break
                time.sleep(0.02)
        finally:
            if os.name != 'nt':
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for child in reversed(list(tracked.values())):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            proc.wait()
    return {'status': 'timeout' if expired else ('ok' if proc.returncode == 0 else 'error'),
            'time_s': time.perf_counter() - start, 'memory_mib': peak / 2**20}


def swept_area(instance, solution):
    """Sum each cutter's full swept union, including outside-field coverage.

    Revisited cells count once per cutter, but overlap between cutters counts
    once for each cutter. A stationary cutter includes its initial footprint.
    """
    import numpy as np
    from cgshop2027_pyutils.grid import CellSet, dilate, rasterize_ring

    cx, cy = instance.cutter_center
    cutter = rasterize_ring(instance.cutter).translated(-cx, -cy)
    total = 0
    for tour in solution.tours:
        x0, y0 = min(tour.x), min(tour.y)
        mask = np.zeros((max(tour.y) - y0 + 1, max(tour.x) - x0 + 1), dtype=bool)
        mask[tour.start[1] - y0, tour.start[0] - x0] = True
        for (ax, ay), (bx, by) in tour.edges():
            if ay == by:
                mask[ay - y0, min(ax, bx) - x0:max(ax, bx) - x0 + 1] = True
            else:
                mask[min(ay, by) - y0:max(ay, by) - y0 + 1, ax - x0] = True
        total += len(dilate(CellSet(mask, (x0, y0)), cutter))
    return total


def worker(args):
    from cgshop2027_pyutils.io import read_instance, read_solution
    from cgshop2027_pyutils.verify import check_for_errors
    instance, solution = read_instance(args[1]), read_solution(args[2])
    errors = check_for_errors(instance, solution)
    if instance.instance_uid != solution.instance_uid:
        errors.append('Instance UID mismatch')
    if args[0] == '--validate':
        Path(args[3]).write_text(json.dumps({'errors': [str(e) for e in errors],
                                           'max_len': solution.max_tour_length,
                                           'swept_area': swept_area(instance, solution) if not errors else None}))
    elif not errors:
        import matplotlib
        matplotlib.use('Agg')
        from cgshop2027_pyutils.visualize import create_solution_animation
        animation = create_solution_animation(instance, solution, max_frames=40, interval=150)
        animation.save(args[3], writer='pillow', dpi=55)
    else:
        raise ValueError('Cannot animate an invalid solution')


def cell(value):
    return str(value).replace('|', '/').replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')


def report(rows, out):
    best = {}
    for row in rows:
        if row['status'] == 'valid':
            best[row['instance']] = min(best.get(row['instance'], math.inf), row['max_len'])
    ranking = []
    for solver in sorted({r['solver'] for r in rows}):
        group = [r for r in rows if r['solver'] == solver]
        valid = [r for r in group if r['status'] == 'valid']
        score = sum(1 if r['max_len'] == 0 else best[r['instance']] / r['max_len'] for r in valid) / len(group)
        ranking.append((len(valid), score, solver, len(group)))
    lines = ['# Solver benchmark', '',
             'Coverage efficiency = field area / sum of per-cutter swept areas.',
             'Only validated solutions receive a score. Each swept area includes the starting footprint and travel outside the field. Overlap between cutters is counted for each cutter.',
             'Time is solver wall time. Memory is sampled peak process-tree RSS (20 ms), not an exact OS high-water mark.',
             'Dependency installation, validation, and animation are excluded from solver measurements.', '',
             '| Solver | Valid | Relative score |', '|---|---:|---:|']
    for valid, score, solver, total in sorted(ranking, key=lambda r: (-r[0], -r[1], r[2])):
        lines.append(f'| {cell(solver)} | {valid}/{total} | {score:.4f} |')
    lines += ['', 'Relative score averages best valid length / solver length on this same sample. Failures score zero.', '',
              '| Solver | Instance (UID) | Status | Efficiency | Max len | Time (s) | Memory (MiB) | Animation |',
              '|---|---|---|---:|---:|---:|---:|---|']
    for r in rows:
        def number(key):
            v = r.get(key)
            return '—' if v is None else f'{v:.3f}'
        animation = f"[GIF]({r['animation']})" if r.get('animation') else '—'
        lines.append(f"| {cell(r['solver'])} | {cell(r['instance'])} | {cell(r['status'])} | {number('efficiency')} | {number('max_len')} | {number('time_s')} | {number('memory_mib')} | {animation} |")
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('instances', type=Path)
    parser.add_argument('solutions', nargs='?', type=Path, help='Validate saved solutions, with no solver timing')
    parser.add_argument('--solver-root', action='append', default=[], metavar='LABEL=PATH')
    parser.add_argument('--sample', type=int, default=None, help='Size-stratified sample count, or 0 for all examples')
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--validation-timeout', type=float, default=60)
    parser.add_argument('--animation-timeout', type=float, default=120)
    parser.add_argument('--animate', action='store_true')
    parser.add_argument('--large', action='store_true', help='Also generate square stress cases of side 256, 1024, and 4096')
    parser.add_argument('--output', type=Path, default=Path('benchmark-results'))
    args = parser.parse_args()
    if args.sample is None:
        args.sample = 0 if args.solutions else 10
    if args.sample < 0 or min(args.timeout, args.validation_timeout, args.animation_timeout) <= 0:
        parser.error('Sample must be nonnegative and timeouts must be positive')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    args.instances = args.instances.resolve()
    paths = sample(list(args.instances.glob('*.instance.json')), args.sample)
    if not paths:
        parser.error('No instances found')
    solvers = []
    for entry in args.solver_root:
        label, root = entry.split('=', 1)
        for folder in sorted(Path(root).resolve().iterdir()):
            if (folder / 'main.py').is_file() and (folder / 'pyproject.toml').is_file():
                solvers.append((f'{label}/{folder.name}', folder))
    if args.solutions:
        solvers.append(('saved-solutions', None))
    if not solvers:
        parser.error('Supply --solver-root LABEL=PATH or a saved solutions directory')
    if args.large:
        for side in (256, 1024, 4096):
            uid = f'generated-square-{side}'
            data = {'content_type': 'CGSHOP2027_Instance', 'instance_uid': uid,
                    'region_to_cover': {'outer_boundary': {'x': [0, side, side, 0], 'y': [0, 0, side, side]}, 'inner_boundaries': []},
                    'cutter': {'x': [0, 4, 4, 0], 'y': [0, 0, 4, 4]}, 'cutter_center': [0, 0], 'number_of_cutters': 3}
            path = out / f'{uid}.instance.json'
            path.write_text(json.dumps(data))
            paths.append(path)
    manifest = [{'uid': json.loads(p.read_text())['instance_uid'], 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
    (out / 'sample.json').write_text(json.dumps(manifest, indent=2))
    def revision(folder):
        result = subprocess.run(['git', '-C', str(folder), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    provenance = {'python': sys.version, 'platform': platform.platform(),
                  'processor': platform.processor(), 'cpu_count': os.cpu_count(),
                  'timeout_s': args.timeout, 'memory_sampling_interval_s': 0.02,
                  'solvers': [{'name': name, 'revision': revision(folder) if folder else None}
                              for name, folder in solvers]}
    (out / 'environment.json').write_text(json.dumps(provenance, indent=2))
    rows = []
    if args.solutions and args.sample == 0:
        expected = {p.name.replace('.instance.json', '.solution.json') for p in paths}
        for extra in sorted(args.solutions.glob('*.solution.json')):
            if extra.name not in expected:
                rows.append({'solver': 'saved-solutions', 'instance': extra.stem,
                             'status': 'unmatched-solution', 'time_s': None, 'memory_mib': None})
    script = str(Path(__file__).resolve())
    for solver, folder in solvers:
        for index, source in enumerate(paths):
            data = json.loads(source.read_text())
            uid = data['instance_uid']
            # Artifact paths never depend on untrusted instance UIDs or solver labels.
            directory = out / f'run-{len(rows):04d}'
            directory.mkdir(exist_ok=True)
            for artifact in ('solution.json', 'validation.json', 'animation.gif'):
                (directory / artifact).unlink(missing_ok=True)
            row = {'solver': solver, 'instance': uid, 'area': area(data), 'cutters': data['number_of_cutters']}
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                inputs, outputs = work / 'inputs', work / 'outputs'
                inputs.mkdir()
                outputs.mkdir()
                shutil.copyfile(source, inputs / 'case.instance.json')
                if folder:
                    command = ['uv', 'run', '--no-sync', '--project', str(folder), 'python', str(folder / 'main.py'), str(outputs), '--instances', str(inputs)]
                    row.update(run(command, args.timeout, directory / 'solver.log', cwd=folder))
                    candidates = list(outputs.glob('*.solution.json'))
                else:
                    candidates = [p for p in args.solutions.glob('*.solution.json') if p.name == source.name.replace('.instance.json', '.solution.json')]
                    row.update(status='ok', time_s=None, memory_mib=None)
                if row['status'] == 'ok' and len(candidates) != 1:
                    row['status'] = 'missing-output' if not candidates else 'multiple-outputs'
                if row['status'] == 'ok':
                    solution = directory / 'solution.json'
                    shutil.copyfile(candidates[0], solution)
                    validation = run([sys.executable, script, '--validate', str(source.resolve()), str(solution), str(directory / 'validation.json')], args.validation_timeout, directory / 'validation.log')
                    row['status'] = 'validation-' + validation['status']
                    if validation['status'] == 'ok':
                        result = json.loads((directory / 'validation.json').read_text())
                        row['status'] = 'invalid' if result['errors'] else 'valid'
                        row['errors'] = result['errors']
                        if row['status'] == 'valid':
                            row['max_len'] = result['max_len']
                            denom = result['swept_area']
                            row['swept_area'] = denom
                            row['efficiency'] = row['area'] / denom if denom else None
                            if args.animate:
                                gif = directory / 'animation.gif'
                                animation = run([sys.executable, script, '--animate', str(source.resolve()), str(solution), str(gif)], args.animation_timeout, directory / 'animation.log')
                                row['animation_status'] = animation['status']
                                if animation['status'] == 'ok' and gif.exists():
                                    row['animation'] = gif.relative_to(out).as_posix()
                rows.append(row)
                print(f"{solver} {uid}: {row['status']}", flush=True)
                (out / 'results.json').write_text(json.dumps(rows, indent=2, allow_nan=False))
                report(rows, out)
    return 1 if any(r['status'] != 'valid' for r in rows) else 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('--validate', '--animate'):
        worker(sys.argv[1:])
    else:
        sys.exit(main())
