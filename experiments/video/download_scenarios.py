"""Deterministic, hash-verified subset from the author's public Mendeley release."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen


def download_one(item, root):
    path = root / item['filename']
    expected = item['content_details']['sha256_hash']
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
        return path.name
    for attempt in range(4):
        try:
            blob = subprocess.check_output(['curl', '-fsSL', '--max-time', '30',
                                            item['content_details']['download_url']], stderr=subprocess.PIPE)
            if hashlib.sha256(blob).hexdigest() != expected:
                raise ValueError('SHA-256 mismatch: ' + path.name)
            path.write_bytes(blob)
            return path.name
        except Exception:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('data/raw/video_research'))
    p.add_argument('--per-sequence', type=int, default=70)
    args = p.parse_args()
    meta = json.loads((args.root / 'scenario_metadata.json').read_text())
    files = {x['filename']: x for x in meta['files']}
    groups = defaultdict(list)
    for name in sorted(files):
        if name.endswith('.jpg'):
            groups[name.split('_')[0]].append(name)
    selected = []
    for seq, names in sorted(groups.items()):
        n = min(args.per_sequence, len(names))
        for i in range(n):
            name = names[round(i * (len(names) - 1) / max(n - 1, 1))]
            selected.extend([files[name], files[Path(name).with_suffix('.txt').name]])
    out = args.root / 'scenarios'
    out.mkdir(parents=True, exist_ok=True)
    index = {'dataset': meta['id'], 'version': meta['version'],
             'metadata_sha256': hashlib.sha256((args.root / 'scenario_metadata.json').read_bytes()).hexdigest(),
             'selection': 'evenly spaced by filename within each sequence, before inference',
             'per_sequence': args.per_sequence, 'files': selected}
    (args.root / 'scenario_subset.json').write_text(json.dumps(index, indent=2))
    errors = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(download_one, item, out): item['filename'] for item in selected}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
            except Exception as e:
                errors.append({'file': futures[future], 'error': str(e)})
            if i % 100 == 0:
                print(f'{i}/{len(futures)} files; errors={len(errors)}', flush=True)
    summary = {'selected_images': len(selected) // 2, 'files': len(selected),
               'downloaded_bytes': sum((out / x['filename']).stat().st_size for x in selected if (out / x['filename']).exists()),
               'sequences': {k: min(args.per_sequence, len(v)) for k, v in groups.items()},
               'errors': errors}
    (args.root / 'download_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
