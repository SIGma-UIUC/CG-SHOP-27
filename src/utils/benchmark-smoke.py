"""Fail early if the CI runner cannot execute or measure benchmark processes."""

from pathlib import Path
import runpy
import sys
import tempfile


def main():
    run = runpy.run_path(str(Path(__file__).with_name('benchmark-run.py')))['run']
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'input').write_text('benchmark smoke test')
        command = [sys.executable, '-c',
                   'from pathlib import Path; '
                   'allocation = bytearray(8 * 1024 * 1024); '
                   'Path("output").write_text(Path("input").read_text())']
        result = run(command, 10, root / 'process.log', cwd=root)
        if (result['status'] != 'ok' or not result['memory_mib']
                or not (root / 'output').is_file()
                or (root / 'output').read_text() != 'benchmark smoke test'):
            raise RuntimeError(f'BenchExec preflight failed: {result}\n'
                               + (root / 'process.log').read_text())
        print(f'BenchExec preflight passed: {result}')


if __name__ == '__main__':
    main()
