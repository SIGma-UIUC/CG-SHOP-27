"""Focused regression checks for benchmark failure reporting and scoring."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace


ROOT = Path(__file__).parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'{name.replace("_", "-")}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkReportTest(unittest.TestCase):
    def test_distinct_suites_have_independent_rankings(self):
        report = load_module('benchmark_report')
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            rows = [
                {'solver': 'candidate/full', 'instance': 'same-uid', 'status': 'valid',
                 'max_len': 10, 'benchmark_suite': 'full'},
                {'solver': 'candidate/tiny', 'instance': 'same-uid', 'status': 'valid',
                 'max_len': 1, 'benchmark_suite': 'tiny'},
                {'solver': 'merged/full', 'instance': 'same-uid', 'status': 'valid',
                 'max_len': 20, 'benchmark_suite': 'full'},
            ]
            report.report([report.public_row(row) for row in rows], output)
            boards = {board['suite']: board['ranking']
                      for board in json.loads((output / 'leaderboard.json').read_text())}
            self.assertEqual(boards['full'], [[1, 1.0, 'candidate/full', 1],
                                              [1, 0.5, 'merged/full', 1]])
            self.assertEqual(boards['tiny'], [[1, 1.0, 'candidate/tiny', 1]])

    def test_stationary_cutter_is_excluded_from_weighted_area(self):
        runner = load_module('benchmark_run')
        self.assertEqual(runner.length_balanced_swept_area([7, 20], [0, 10]), 20)
        self.assertIsNone(runner.length_balanced_swept_area([7, 20], [0, 0]))

    def test_report_retains_a_failed_solver_row(self):
        report = load_module('benchmark_report')
        row = report.public_row({
            'solver': 'candidate/fails', 'instance': 'tiny', 'status': 'timeout',
            'time_s': 30.0, 'memory_mib': 12.0, 'private_log_path': '/secret',
        })
        self.assertEqual(row, {'solver': 'candidate/fails', 'instance': 'tiny',
                               'status': 'timeout', 'time_s': 30.0, 'memory_mib': 12.0})

    def test_failed_solver_run_produces_a_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            instances, solver, dumps, report = (root / name for name in ('instances', 'solver', 'dumps', 'report'))
            instances.mkdir()
            solver.mkdir()
            (instances / 'tiny.instance.json').write_text(json.dumps({
                'instance_uid': 'tiny', 'number_of_cutters': 1,
                'region_to_cover': {
                    'outer_boundary': {'x': [0, 1, 1, 0], 'y': [0, 0, 1, 1]},
                    'inner_boundaries': [],
                },
            }))
            (solver / 'main.py').write_text('raise SystemExit(2)\n')
            (solver / 'pyproject.toml').write_text(
                '[project]\nname = "fails"\nversion = "0"\nrequires-python = ">=3.14"\n')
            failed = subprocess.run([
                sys.executable, ROOT / 'benchmark-run.py', instances,
                '--solver-root', f'candidate={root}', '--solver', 'solver',
                '--timeout', '1', '--output', dumps,
            ])
            self.assertNotEqual(failed.returncode, 0)
            manifest = root / 'manifest.json'
            manifest.write_text('[]\n')
            subprocess.run([sys.executable, ROOT / 'benchmark-report.py', '--dumps', dumps,
                            '--manifest', manifest, '--output', report], check=True)
            rows = json.loads((report / 'results.json').read_text())
            self.assertEqual(len(rows), 1)
            self.assertNotEqual(rows[0]['status'], 'valid')
            self.assertTrue((report / 'report.md').is_file())


class SolverInstancesTest(unittest.TestCase):
    def setUp(self):
        self.runner = load_module('benchmark_run')
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.solver = self.root / 'solver'
        self.solver.mkdir()
        self.project = self.solver / 'pyproject.toml'
        self.project.write_text('[project]\nname = "test"\nversion = "0"\n')
        self.custom = self.solver / 'examples/instances'
        self.custom.mkdir(parents=True)
        self.case = self.custom / 'tiny.instance.json'
        self.case.write_text('{"instance_uid": "tiny", "size": 1}\n')
        self.default = self.root / 'default.instance.json'
        self.default.write_text('{"instance_uid": "default"}\n')

    def configure(self, directory='examples/instances'):
        self.project.write_text('[tool.sigma.benchmark]\ninstances = ' + json.dumps(directory) + '\n')

    def test_override_and_default_use_their_own_inputs(self):
        self.assertEqual(self.runner.solver_instance_paths(self.solver, [self.default]), [self.default])
        self.configure()
        self.assertEqual(self.runner.solver_instance_paths(self.solver, [self.default]), [self.case])
        # A custom suite does not require the default input directory to contain files.
        self.assertEqual(self.runner.solver_instance_paths(self.solver, []), [self.case])

    def test_invalid_overrides_fail_without_falling_back(self):
        for directory in ('missing', '.', '', '../', str(self.custom), 42):
            with self.subTest(directory=directory):
                self.configure(directory)
                with self.assertRaises(ValueError):
                    self.runner.solver_instance_paths(self.solver, [self.default])

    def test_duplicate_uids_are_rejected(self):
        duplicate = self.custom / 'duplicate.instance.json'
        duplicate.write_bytes(self.case.read_bytes())
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.runner.instance_manifest([self.case, duplicate])

    def test_main_routes_each_solver_to_its_selected_suite(self):
        self.configure()
        shared = self.root / 'shared'
        shared.mkdir()
        (shared / 'main.py').write_text('')
        (shared / 'pyproject.toml').write_text('[project]\nname = "shared"\nversion = "0"\n')
        (self.solver / 'main.py').write_text('')
        default_dir = self.root / 'default'
        default_dir.mkdir()
        self.default.rename(default_dir / self.default.name)
        seen = []

        def run_case(solver, folder, source, *args):
            uid = json.loads(source.read_text())['instance_uid']
            seen.append((solver, uid))
            return {'solver': solver, 'instance': uid, 'status': 'error'}

        command = ['benchmark-run.py', str(default_dir), '--solver-root', f'candidate={self.root}',
                   '--output', str(self.root / 'output')]
        with patch.object(sys, 'argv', command), patch.object(self.runner, 'evaluate_instance', run_case):
            self.assertEqual(self.runner.main(), 1)
        self.assertEqual(seen, [('candidate/shared', 'default'), ('candidate/solver', 'tiny')])
        rows = json.loads((self.root / 'output/raw-results.json').read_text())
        self.assertNotEqual(rows[0]['benchmark_suite'], rows[1]['benchmark_suite'])

    @unittest.skipUnless(shutil.which('bash'), 'Requires bash')
    def test_fixture_only_changes_are_detected_by_workflow(self):
        work = self.root / 'workflow'
        candidate = work / 'candidate/src/solver/custom'
        merged = work / 'merged/src/solver/custom'
        candidate.parent.mkdir(parents=True)
        merged.parent.mkdir(parents=True)
        shutil.copytree(self.solver, candidate)
        shutil.copytree(self.solver, merged)
        (candidate / 'examples/instances/tiny.instance.json').write_text('{"instance_uid": "changed"}\n')
        subprocess.run(['bash', ROOT.resolve().parents[1] / '.github/scripts/solver-benchmark.sh',
                        'find-changed'], cwd=work, env={**os.environ, 'GITHUB_EVENT_NAME': 'pull_request',
                        'GITHUB_OUTPUT': str(work / 'outputs')}, check=True)
        self.assertEqual((work / 'changed.txt').read_text(), 'custom\n')

    def test_suite_identity_uses_contents_and_not_checkout_paths(self):
        def evaluate(paths):
            output = self.root / 'output'
            output.mkdir(exist_ok=True)
            manifest = self.runner.instance_manifest(paths)
            with patch.object(self.runner, 'evaluate_instance', return_value={
                    'solver': 'candidate/test', 'instance': 'tiny', 'status': 'error'}):
                self.runner.evaluate([('candidate/test', self.solver, paths, manifest)],
                                     SimpleNamespace(), output)
            return json.loads((output / 'raw-results.json').read_text())[0]

        original = evaluate([self.case])
        copy = self.root / 'copy.instance.json'
        copy.write_bytes(self.case.read_bytes())
        self.assertEqual(evaluate([copy])['benchmark_suite'], original['benchmark_suite'])
        copy.write_text('{"instance_uid": "tiny", "size": 2}\n')
        changed = evaluate([copy])
        self.assertNotEqual(changed['benchmark_suite'], original['benchmark_suite'])
        self.assertNotEqual(changed['instance_sha256'], original['instance_sha256'])

    def test_custom_fixture_edits_invalidate_baseline_fingerprint(self):
        baseline = load_module('benchmark_baseline')
        self.configure()
        before = baseline.fingerprint(self.solver)
        self.case.write_text('{"instance_uid": "tiny", "size": 2}\n')
        self.assertNotEqual(baseline.fingerprint(self.solver), before)


@unittest.skipUnless(shutil.which('bash') and shutil.which('jq'), 'Requires bash and jq')
class BenchmarkWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        utilities = self.work / 'candidate/src/utils'
        utilities.mkdir(parents=True)
        for name in ('benchmark-baseline.py', 'benchmark-report.py'):
            shutil.copyfile(ROOT / name, utilities / name)
        python = utilities / '.venv/bin/python'
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        (self.work / 'benchmark-inputs').mkdir()
        (self.work / 'benchmark-inputs/manifest.json').write_text('[]\n')
        (self.work / 'cache-key.txt').write_text('test-key\n')
        (self.work / 'removed.txt').write_text('')
        self.solver_root = self.work / 'merged/src/solver'
        self.solver_root.mkdir(parents=True)

    def run_command(self, command):
        subprocess.run(['bash', ROOT.resolve().parents[1] / '.github/scripts/solver-benchmark.sh', command],
                       cwd=self.work, env={**os.environ, 'GITHUB_OUTPUT': str(self.work / 'outputs')},
                       check=True, capture_output=True, text=True)

    def add_solver(self, name):
        folder = self.solver_root / name
        folder.mkdir()
        (folder / 'main.py').write_text('')
        (folder / 'pyproject.toml').write_text('')

    def test_new_solver_is_not_a_missing_merged_solver(self):
        for existing in (False, True):
            with self.subTest(existing_merged_solver=existing):
                names = ['z-new']
                if existing:
                    self.add_solver('a-existing')
                    names.insert(0, 'a-existing')
                (self.work / 'changed.txt').write_text('\n'.join(names) + '\n')
                (self.work / 'baseline.json').write_text('{}\n')
                self.run_command('select-baseline')
                self.assertEqual((self.work / 'missing.txt').read_text(),
                                 'a-existing\n' if existing else '')
                self.assertIn(f'has-missing={str(existing).lower()}\n',
                              (self.work / 'outputs').read_text())

    def test_partial_cache_miss_preserves_both_merged_rows(self):
        self.add_solver('cached')
        self.add_solver('uncached')
        cached = {'solver': 'merged/cached', 'instance': 'tiny', 'status': 'valid', 'max_len': 10}
        fresh = {'solver': 'merged/uncached', 'instance': 'tiny', 'status': 'timeout'}
        baseline = load_module('benchmark_baseline')
        (self.work / 'baseline.json').write_text(json.dumps({
            'schema_version': 2, 'cache_key': 'test-key', 'sample': [],
            'solvers': {'cached': {'fingerprint': baseline.fingerprint(self.solver_root / 'cached'),
                                   'rows': [cached]}},
        }))
        (self.work / 'changed.txt').write_text('cached\nuncached\n')
        self.run_command('select-baseline')
        self.assertEqual((self.work / 'missing.txt').read_text(), 'uncached\n')
        dumps = self.work / 'merged-dumps'
        dumps.mkdir()
        (dumps / 'raw-results.json').write_text(json.dumps([fresh]))
        self.run_command('report-merged')
        self.assertEqual(json.loads((self.work / 'prior-results.json').read_text()), [cached, fresh])
        self.run_command('report-empty')
        self.assertEqual(json.loads((self.work / 'benchmark-results/results.json').read_text()),
                         [cached, fresh])


if __name__ == '__main__':
    unittest.main()
