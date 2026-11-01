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


ROOT = Path(__file__).parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'{name.replace("_", "-")}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkReportTest(unittest.TestCase):
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
