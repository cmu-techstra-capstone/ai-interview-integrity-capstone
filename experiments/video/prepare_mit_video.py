"""Verify/extract the authorized MIT Videos.zip into ignored local storage.

Never executes archive contents. Only expected P#/PP# AVI files are written;
archive paths are not used as output paths. ZIP CRC is checked while streaming.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile


def hash_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare(archive, out):
    out.mkdir(parents=True, exist_ok=True)
    inventory = []
    with zipfile.ZipFile(archive) as z:
        members = [m for m in z.infolist() if not m.is_dir()
                   and not m.filename.startswith('__MACOSX/')
                   and Path(m.filename).suffix.lower() == '.avi']
        names = [Path(m.filename).name for m in members]
        if not members or any(not re.fullmatch(r'PP?\d+\.avi', n, re.I) for n in names):
            raise ValueError('Unexpected MIT video archive layout; inspect before extraction.')
        if len({n.lower() for n in names}) != len(names):
            raise ValueError('Duplicate output names in archive.')
        required = sum(m.file_size for m in members if not (out / Path(m.filename).name).exists())
        if shutil.disk_usage(out).free < required + 1024 ** 3:
            raise ValueError('Insufficient space: require expanded videos plus 1 GiB reserve.')
        for member, name in zip(members, names):
            dest = out / name
            digest = hashlib.sha256()
            written = 0
            # Existing files are revalidated against the archive rather than silently reused.
            if dest.exists():
                with z.open(member) as f:
                    for block in iter(lambda: f.read(1 << 20), b''):
                        digest.update(block)
                        written += len(block)
                if dest.stat().st_size != written or hash_file(dest) != digest.hexdigest():
                    raise ValueError('Existing video differs from archive: ' + name)
            else:
                partial = dest.with_suffix('.avi.partial')
                with z.open(member) as source, partial.open('wb') as target:
                    for block in iter(lambda: source.read(1 << 20), b''):
                        target.write(block)
                        digest.update(block)
                        written += len(block)
                if written != member.file_size:
                    raise ValueError('Unexpected extracted size: ' + name)
                partial.replace(dest)
            inventory.append({'filename': name, 'bytes': written, 'sha256': digest.hexdigest()})
            print(f'Validated {len(inventory)}/{len(members)}', flush=True)
    counts = Counter(int(re.search(r'\d+', n)[0]) for n in names)
    summary = {'archive_filename': archive.name, 'archive_bytes': archive.stat().st_size,
        'archive_sha256': hash_file(archive), 'videos': len(inventory),
        'participants': len(counts), 'participants_with_two_videos': sum(v == 2 for v in counts.values()),
        'expanded_bytes': sum(m['bytes'] for m in inventory),
        'zip_crc': 'passed on all extracted AVI members', 'files': inventory}
    (out.parent / 'video_archive_inventory.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k != 'files'}, indent=2))
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('archive', type=Path)
    p.add_argument('--out', type=Path, default=Path('data/raw/video_research/mit/videos'))
    args = p.parse_args()
    prepare(args.archive, args.out)
