"""Store and retrieve verified benchmark rows for the merged solver revision."""

import argparse
import hashlib
import json
from pathlib import Path


IGNORED = {'.venv', '__pycache__', '.git'}


def fingerprint(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or any(part in IGNORED for part in path.parts) or path.suffix in {'.pyc', '.pyo'}:
            continue
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def solver_fingerprints(root: Path) -> dict[str, str]:
    return {folder.name: fingerprint(folder) for folder in sorted(root.iterdir())
            if (folder / 'main.py').is_file() and (folder / 'pyproject.toml').is_file()}


def read_json(path: Path):
    return json.loads(path.read_text())


def write(args) -> None:
    rows = read_json(args.results)
    manifest = read_json(args.sample)
    solvers = {}
    for name, digest in solver_fingerprints(args.solver_root).items():
        solver_rows = []
        for row in rows:
            if row.get('solver') == f'candidate/{name}':
                cached = dict(row)
                cached['solver'] = f'merged/{name}'
                cached.pop('animation', None)
                solver_rows.append(cached)
        if solver_rows:
            solvers[name] = {'fingerprint': digest, 'rows': solver_rows}
    args.output.write_text(json.dumps({'schema_version': 2, 'cache_key': args.cache_key,
                                       'sample': manifest, 'solvers': solvers}, indent=2) + '\n')


def select(args) -> None:
    cache = read_json(args.baseline) if args.baseline.is_file() else {}
    current_sample = read_json(args.sample)
    cached = (cache.get('solvers', {})
              if cache.get('schema_version') == 2 and cache.get('cache_key') == args.cache_key
              and cache.get('sample') == current_sample else {})
    roots = solver_fingerprints(args.solver_root)
    rows, missing = [], []
    for name in args.solver:
        record = cached.get(name)
        if record and record.get('fingerprint') == roots.get(name) and isinstance(record.get('rows'), list):
            rows.extend(record['rows'])
        else:
            missing.append(name)
    args.output.write_text(json.dumps({'rows': rows, 'missing': missing}, indent=2) + '\n')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)
    store = commands.add_parser('write')
    store.add_argument('--results', type=Path, required=True)
    store.add_argument('--sample', type=Path, required=True)
    store.add_argument('--solver-root', type=Path, required=True)
    store.add_argument('--output', type=Path, required=True)
    store.add_argument('--cache-key', required=True)
    store.set_defaults(func=write)
    retrieve = commands.add_parser('select')
    retrieve.add_argument('--baseline', type=Path, required=True)
    retrieve.add_argument('--sample', type=Path, required=True)
    retrieve.add_argument('--solver-root', type=Path, required=True)
    retrieve.add_argument('--solver', action='append', required=True)
    retrieve.add_argument('--output', type=Path, required=True)
    retrieve.add_argument('--cache-key', required=True)
    retrieve.set_defaults(func=select)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
