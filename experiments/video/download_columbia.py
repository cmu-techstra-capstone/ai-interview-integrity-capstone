"""Range-download all 21 frontal-head gaze targets for all 56 Columbia subjects.

Download only public archive bytes. Verify original ZIP CRC, preserve filename labels,
and write a frozen manifest before feature extraction. No source files enter Git.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import zlib

from interview_integrity.storage.remote_zip import open_remote_zip

URL = 'https://ceal.cs.columbia.edu/static/materials/columbiagaze/columbia_gaze_data_set.zip'
ROOT = Path('data/raw/video_research/columbia')


def download_subject(items):
    start = min(x.header_offset for x in items)
    # Last member local header has variable filename/extra fields; generous 4 KiB margin.
    last = max(items, key=lambda x: x.header_offset)
    end = last.header_offset + last.compress_size + 4096
    blob = subprocess.check_output(['curl', '-fsSL', '--retry', '2', '--max-time', '90',
                                    '-r', f'{start}-{end}', URL], stderr=subprocess.PIPE)
    if len(blob) != end - start + 1:
        raise ValueError('Unexpected HTTP range size')
    records = []
    for info in items:
        offset = info.header_offset - start
        header = struct.unpack_from('<4s5H3I2H', blob, offset)
        if header[0] != b'PK\x03\x04' or header[2] & 1:
            raise ValueError('Unsupported/encrypted member')
        begin = offset + 30 + header[-2] + header[-1]
        payload = blob[begin:begin + info.compress_size]
        data = zlib.decompress(payload, -15) if info.compress_type == 8 else payload
        if len(data) != info.file_size or zlib.crc32(data) != info.CRC:
            raise ValueError('ZIP CRC mismatch')
        filename = Path(info.filename).name
        (ROOT / filename).write_bytes(data)
        m = re.fullmatch(r'(\d+)_2m_(-?\d+)P_(-?\d+)V_(-?\d+)H.jpg', filename)
        records.append({'file': filename, 'participant': m[1], 'head_deg': int(m[2]),
                        'gaze_vertical_deg': int(m[3]), 'gaze_horizontal_deg': int(m[4]),
                        'sha256': hashlib.sha256(data).hexdigest(), 'zip_crc32': info.CRC})
    return records, len(blob)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    archive, raw = open_remote_zip(URL)
    selected = [i for i in archive.infolist() if re.fullmatch(r'Columbia Gaze Data Set/\d+/\d+_2m_0P_-?\d+V_-?\d+H.jpg', i.filename)]
    groups = {}
    for info in selected:
        groups.setdefault(Path(info.filename).name.split('_')[0], []).append(info)
    if len(groups) != 56 or any(len(v) != 21 for v in groups.values()):
        raise ValueError('Unexpected dataset layout')
    # Fixed cohort definition before reading model outputs.
    (ROOT / 'selection.json').write_text(json.dumps({'url': URL, 'archive_size': raw.size,
        'rule': 'all 56 subjects, head pose 0 degrees, all 21 gaze targets',
        'images': [i.filename for i in selected],
        'binary_task': 'abs horizontal >=10 or abs vertical >=10 degrees; negatives horizontal -5/0/5 and vertical 0'}, indent=2))
    records = []; transferred = raw.bytes_fetched
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(download_subject, items) for items in groups.values()]
        for i, f in enumerate(as_completed(futures), 1):
            r, n = f.result(); records.extend(r); transferred += n
            if i % 8 == 0: print(f'{i}/56 participants downloaded', flush=True)
    archive.close()
    summary = {'url': URL, 'archive_bytes': raw.size, 'transferred_bytes': transferred,
               'saved_bytes': sum((ROOT / r['file']).stat().st_size for r in records),
               'participants': 56, 'images': len(records), 'records': sorted(records, key=lambda x:x['file'])}
    (ROOT / 'manifest.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!='records'},indent=2))


if __name__ == '__main__': main()
