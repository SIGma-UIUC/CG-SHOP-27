"""Run solvers on benchmark instances and write measurements and diagnostics."""

import argparse
import json
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


VALIDATION_TIMEOUT = 60
ANIMATION_TIMEOUT = 120


def area(data):
    def polygon(p):
        pts = list(zip(p['x'], p['y']))
        return abs(sum(x * v - u * y for (x, y), (u, v) in zip(pts, pts[1:] + pts[:1]))) / 2
    region = data['region_to_cover']
    return polygon(region['outer_boundary']) - sum(polygon(p) for p in region.get('inner_boundaries', []))


def portable_run(command, timeout, log, cwd=None):
    """Run with psutil when cgroup-based measurement is unavailable."""
    start, peak, tracked = time.perf_counter(), 0, {}
    with log.open('wb') as stream:
        proc = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=os.name != 'nt')
        parent, expired = psutil.Process(proc.pid), False
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


def run(command, timeout, log, cwd=None):
    """Measure Linux runs with BenchExec and use psutil only off Linux."""
    if sys.platform != 'linux':
        return portable_run(command, timeout, log, cwd)
    from benchexec.runexecutor import RunExecutor
    from benchexec.container import DIR_FULL_ACCESS
    try:
        # Inputs and outputs live in host temporary directories. Keep these
        # visible and persist writes instead of hiding them in an overlay.
        executor = RunExecutor(dir_modes={'/': DIR_FULL_ACCESS}, container_system_config=False)
        result = executor.execute_run(args=command, output_filename=str(log),
                                           workingDir=str(cwd) if cwd else None,
                                           walltimelimit=timeout, write_header=False)
    except Exception as error:
        with log.open('a') as stream:
            stream.write(f'BenchExec failed to measure this run: {error}\n')
        return {'status': 'measurement-error', 'time_s': None, 'memory_mib': None}
    if 'walltime' not in result:
        return {'status': 'measurement-error', 'time_s': None, 'memory_mib': None}
    exitcode, memory = result.get('exitcode'), result.get('memory')
    return {
        'status': 'timeout' if result.get('terminationreason') == 'walltime'
        else ('ok' if exitcode is not None and exitcode.value == 0 else 'error'),
        'time_s': float(result['walltime']),
        'memory_mib': float(memory) / 2**20 if memory is not None else None,
    }


def swept_areas_and_lengths(instance, solution):
    """Measure each cutter's swept area and trajectory length.

    A tour starts by covering one cutter footprint.  Every later edge contributes
    only the additional area swept while moving from its start placement to its
    end placement.  This counts overlap with earlier edges again, so following
    the same tour ten times incurs roughly ten times its swept area.
    """
    import numpy as np
    from cgshop2027_pyutils.grid import CellSet, dilate, rasterize_ring

    cx, cy = instance.cutter_center
    cutter = rasterize_ring(instance.cutter).translated(-cx, -cy)
    swept_areas, lengths = [], []
    for tour in solution.tours:
        edges = list(tour.edges())
        swept = len(cutter)
        length = 0
        for (ax, ay), (bx, by) in edges:
            if ax != bx and ay != by:
                raise ValueError('Only axis-aligned tour edges are supported')
            x0, y0 = min(ax, bx), min(ay, by)
            mask = np.zeros((abs(by - ay) + 1, abs(bx - ax) + 1), dtype=bool)
            if ay == by:
                mask[ay - y0, min(ax, bx) - x0:max(ax, bx) - x0 + 1] = True
            else:
                mask[min(ay, by) - y0:max(ay, by) - y0 + 1, ax - x0] = True
            # The footprint at the edge's first endpoint was already counted:
            # initially for the first edge, and by the preceding edge after it.
            swept += len(dilate(CellSet(mask, (x0, y0)), cutter)) - len(cutter)
            length += abs(bx - ax) + abs(by - ay)
        swept_areas.append(swept)
        lengths.append(length)
    return swept_areas, lengths


def efficiency(instance, solution):
    """Return field area divided by length-balanced swept area.

    For cutter i, its swept area is weighted by max tour length / its own tour
    length.  A zero-length cutter cannot contribute to this ratio, so it is
    excluded unless every cutter is stationary.
    """
    swept_areas, lengths = swept_areas_and_lengths(instance, solution)
    weighted_swept_area = length_balanced_swept_area(swept_areas, lengths)
    if weighted_swept_area is None:
        return None, swept_areas, lengths
    return area(instance.model_dump(mode='json')) / weighted_swept_area, swept_areas, lengths


def length_balanced_swept_area(swept_areas, lengths):
    """Exclude stationary cutters unless every cutter is stationary."""
    max_length = max(lengths, default=0)
    if max_length == 0:
        return None
    return sum(
        swept * max_length / length
        for swept, length in zip(swept_areas, lengths)
        if length > 0
    )


def validate_solution(instance_path, solution_path):
    from cgshop2027_pyutils.io import read_instance, read_solution
    from cgshop2027_pyutils.verify import check_for_errors
    instance, solution = read_instance(instance_path), read_solution(solution_path)
    errors = check_for_errors(instance, solution)
    if instance.instance_uid != solution.instance_uid:
        errors.append('Instance UID mismatch')
    if errors:
        return {'errors': [str(e) for e in errors], 'max_len': solution.max_tour_length}
    value, per_tour_swept_areas, tour_lengths = efficiency(instance, solution)
    return {
        'errors': [], 'max_len': solution.max_tour_length, 'efficiency': value,
        'swept_area': sum(per_tour_swept_areas),
        'per_tour_swept_areas': per_tour_swept_areas, 'tour_lengths': tour_lengths,
    }


def create_animation(instance_path, solution_path, destination):
    result = validate_solution(instance_path, solution_path)
    if result['errors']:
        raise ValueError('Cannot animate an invalid solution')
    import matplotlib
    matplotlib.use('Agg')
    from cgshop2027_pyutils.io import read_instance, read_solution
    from cgshop2027_pyutils.visualize import create_solution_animation
    animation = create_solution_animation(read_instance(instance_path), read_solution(solution_path),
                                          max_frames=40, interval=150)
    animation.save(destination, writer='pillow', dpi=55)


def worker(args):
    action, instance_path, solution_path, destination = args
    if action == '--validate':
        Path(destination).write_text(json.dumps(validate_solution(instance_path, solution_path)))
    else:
        create_animation(instance_path, solution_path, destination)

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('instances', type=Path, help='The instances directory from benchmark-instances.py')
    parser.add_argument('--solver-root', action='append', default=[], metavar='LABEL=PATH')
    parser.add_argument('--solver', action='append', default=[], metavar='NAME',
                        help='Evaluate only these solver directory names (repeatable)')
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--animate', action='store_true')
    parser.add_argument('--output', type=Path, required=True, help='New raw dump directory')
    return parser, parser.parse_args()


def discover_solvers(args, parser):
    solvers, requested = [], set(args.solver)
    for entry in args.solver_root:
        label, root = entry.split('=', 1)
        for folder in sorted(Path(root).resolve().iterdir()):
            if (folder / 'main.py').is_file() and (folder / 'pyproject.toml').is_file() and (not requested or folder.name in requested):
                solvers.append((f'{label}/{folder.name}', folder))
    found = {folder.name for _, folder in solvers if folder}
    missing = requested - found
    if missing:
        parser.error('Requested solver directories not found: ' + ', '.join(sorted(missing)))
    if not solvers:
        parser.error('Supply --solver-root LABEL=PATH')
    return solvers


def revision(folder):
    result = subprocess.run(['git', '-C', str(folder), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def write_environment(out, args, solvers):
    provenance = {'python': sys.version, 'platform': platform.platform(),
                  'processor': platform.processor(), 'cpu_count': os.cpu_count(),
                  'timeout_s': args.timeout, 'resource_measurement': 'BenchExec on Linux, psutil elsewhere',
                  'solvers': [{'name': name, 'revision': revision(folder) if folder else None}
                              for name, folder in solvers]}
    (out / 'environment.json').write_text(json.dumps(provenance, indent=2))


def evaluate_instance(solver, folder, source, args, out, script, index):
    data = json.loads(source.read_text())
    directory = out / f'run-{index:04d}'
    directory.mkdir(exist_ok=True)
    for artifact in ('solution.json', 'validation.json', 'animation.gif'):
        (directory / artifact).unlink(missing_ok=True)
    row = {'solver': solver, 'instance': data['instance_uid'], 'area': area(data), 'cutters': data['number_of_cutters']}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        inputs, outputs = work / 'inputs', work / 'outputs'
        inputs.mkdir()
        outputs.mkdir()
        shutil.copyfile(source, inputs / 'case.instance.json')
        command = ['uv', 'run', '--no-sync', '--project', str(folder), 'python', str(folder / 'main.py'), str(outputs), '--instances', str(inputs)]
        row.update(run(command, args.timeout, directory / 'solver.log', cwd=folder))
        candidates = list(outputs.glob('*.solution.json'))
        if row['status'] == 'ok' and len(candidates) != 1:
            row['status'] = 'missing-output' if not candidates else 'multiple-outputs'
        if row['status'] == 'ok':
            validate_candidate(row, candidates[0], source, directory, script)
        if row['status'] == 'valid' and args.animate:
            animate_candidate(row, source, directory, script, out)
    return row


def validate_candidate(row, candidate, source, directory, script):
    solution = directory / 'solution.json'
    shutil.copyfile(candidate, solution)
    validation = run([sys.executable, script, '--validate', str(source.resolve()),
                      str(solution), str(directory / 'validation.json')], VALIDATION_TIMEOUT,
                     directory / 'validation.log')
    row['status'] = 'validation-' + validation['status']
    if validation['status'] != 'ok':
        return
    result = json.loads((directory / 'validation.json').read_text())
    row['status'] = 'invalid' if result['errors'] else 'valid'
    row['errors'] = result['errors']
    if row['status'] == 'valid':
        row.update({key: result[key] for key in ('max_len', 'swept_area',
                   'per_tour_swept_areas', 'tour_lengths', 'efficiency')})


def animate_candidate(row, source, directory, script, output):
    gif = directory / 'animation.gif'
    animation = run([sys.executable, script, '--animate', str(source.resolve()),
                     str(directory / 'solution.json'), str(gif)], ANIMATION_TIMEOUT,
                    directory / 'animation.log')
    row['animation_status'] = animation['status']
    if animation['status'] == 'ok' and gif.exists():
        row['animation'] = gif.relative_to(output).as_posix()


def evaluate(solvers, paths, args, out):
    rows = []
    script = str(Path(__file__).resolve())
    (out / 'raw-results.json').write_text('[]\n')
    for solver, folder in solvers:
        for source in paths:
            row = evaluate_instance(solver, folder, source, args, out, script, len(rows))
            rows.append(row)
            print(f"{solver} {row['instance']}: {row['status']}", flush=True)
            (out / 'raw-results.json').write_text(json.dumps(rows, indent=2, allow_nan=False) + '\n')


def main():
    parser, args = parse_args()
    if args.timeout <= 0:
        parser.error('Timeout must be positive')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    args.instances = args.instances.resolve()
    paths = sorted(args.instances.glob('*.instance.json'))
    if not paths:
        parser.error('No instances found')
    solvers = discover_solvers(args, parser)
    write_environment(out, args, solvers)
    evaluate(solvers, paths, args, out)
    rows = json.loads((out / 'raw-results.json').read_text())
    return 1 if any(row['status'] != 'valid' for row in rows) else 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('--validate', '--animate'):
        worker(sys.argv[1:])
    else:
        sys.exit(main())
