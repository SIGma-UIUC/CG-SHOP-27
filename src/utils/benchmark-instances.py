"""Copy a reproducible set of benchmark instances and write its manifest."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil


BENCHMARK_INSTANCES = (
    'srpg_11k_305_1d6.instance.json', 'fpg73_1k_1s2.instance.json',
    'iso_725k_1813_3d6.instance.json', 'octa_3k_3k_1s2.instance.json',
    'smr_275k_4k_3p.instance.json', 'fpg73_20k_1s2.instance.json',
    'smr_89k_11k_3s4.instance.json', 'pla7k_15k_1p.instance.json',
    'smr_1439_25k_2p.instance.json', 'smo_1639_26k_1l1.instance.json',
    'xrh24k_30k_1p.instance.json', 'octa_25k_30k_3l1.instance.json',
    'usa14k_75k_1p.instance.json', 'pla34k_75k_2p.instance.json',
    'isoa_13m_98k_3l1.instance.json',
)


def polygon_area(data):
    def area(polygon):
        points = list(zip(polygon['x'], polygon['y']))
        return abs(sum(x * v - u * y for (x, y), (u, v) in zip(points, points[1:] + points[:1]))) / 2
    region = data['region_to_cover']
    return area(region['outer_boundary']) - sum(area(p) for p in region.get('inner_boundaries', []))


def stratified_sample(paths, count):
    ordered = sorted(paths, key=lambda p: (polygon_area(json.loads(p.read_text())), p.name))
    if count == 0 or count >= len(ordered):
        return ordered
    selected, families = [], set()
    for index in range(count):
        bucket = ordered[index * len(ordered) // count:(index + 1) * len(ordered) // count]
        selected.append(next((p for p in bucket if p.name.split('_')[0] not in families), bucket[len(bucket) // 2]))
        families.add(selected[-1].name.split('_')[0])
    return selected


def generated_large_instances():
    for side in (256, 1024, 4096):
        uid = f'generated-square-{side}'
        yield uid, json.dumps({
            'content_type': 'CGSHOP2027_Instance', 'instance_uid': uid,
            'region_to_cover': {'outer_boundary': {'x': [0, side, side, 0], 'y': [0, 0, side, side]}, 'inner_boundaries': []},
            'cutter': {'x': [0, 4, 4, 0], 'y': [0, 0, 4, 4]},
            'cutter_center': [0, 0], 'number_of_cutters': 3,
        })


def select_instances(source, sample, parser):
    if sample == 15:
        paths = [source / name for name in BENCHMARK_INSTANCES]
        missing = [path.name for path in paths if not path.is_file()]
        if missing:
            parser.error('Missing fixed benchmark instances: ' + ', '.join(missing))
        return paths
    return stratified_sample(list(source.glob('*.instance.json')), sample)


def copy_instance(source, destination):
    shutil.copyfile(source, destination)
    return {'uid': json.loads(destination.read_text())['instance_uid'],
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


def prepare_instances(source, output, sample, include_large, parser):
    paths = select_instances(source, sample, parser)
    if not paths:
        parser.error('No instances found')
    instances = output / 'instances'
    instances.mkdir(parents=True, exist_ok=True)
    manifest = [copy_instance(path, instances / path.name) for path in paths]
    if include_large:
        for uid, encoded in generated_large_instances():
            destination = instances / f'{uid}.instance.json'
            destination.write_text(encoded)
            manifest.append({'uid': uid, 'sha256': hashlib.sha256(encoded.encode()).hexdigest()})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Directory containing .instance.json files')
    parser.add_argument('--output', type=Path, required=True, help='New benchmark-inputs directory')
    parser.add_argument('--sample', type=int, default=15, help='0 means all available instances')
    parser.add_argument('--large', action='store_true', help='Also include generated stress instances')
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    prepare_instances(source, output, args.sample, args.large, parser)


if __name__ == '__main__':
    main()
