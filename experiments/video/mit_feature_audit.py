"""Audit official MIT interview features without treating ratings as AI-use labels.

Reads ZIP members in memory; does not extract or publish participant features.
The distributed Pitch/Yaw/Roll values have no documented physical units, so this
script deliberately applies no degree thresholds or transferred classifiers.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def audit(features_zip, labels_zip, out):
    records = []
    headers = Counter()
    with zipfile.ZipFile(features_zip) as z:
        bad = z.testzip()
        if bad:
            raise ValueError('CRC failure: ' + bad)
        members = sorted(n for n in z.namelist() if n.endswith('.csv') and not n.startswith('__MACOSX/'))
        for name in members:
            identifier = Path(name).stem.lower()
            if not re.fullmatch(r'pp?\d+', identifier):
                raise ValueError('Unexpected interview identifier: ' + identifier)
            content = z.read(name).decode('utf-8-sig')
            header = [h.strip() for h in content.splitlines()[0].split(',') if h.strip()]
            headers[tuple(header)] += 1
            data = np.genfromtxt(io.StringIO(content), delimiter=',', skip_header=1,
                                 usecols=range(len(header)), ndmin=2)
            finite = np.isfinite(data)
            pose = data[:, :3]
            records.append({'id': identifier, 'participant': int(re.search(r'\d+', identifier)[0]),
                'condition': 'post_counseling' if identifier.startswith('pp') else 'pre_counseling',
                'rows': len(data), 'columns': len(header),
                'nonfinite_values': int((~finite).sum()),
                'rows_with_nonfinite_values': int((~finite).any(axis=1).sum()),
                'all_zero_rows': int(np.all(data == 0, axis=1).sum()),
                'pose_min': np.nanmin(pose, axis=0).tolist(),
                'pose_median': np.nanmedian(pose, axis=0).tolist(),
                'pose_max': np.nanmax(pose, axis=0).tolist()})
    with zipfile.ZipFile(labels_zip) as z:
        bad = z.testzip()
        if bad:
            raise ValueError('CRC failure: ' + bad)
        scores = list(csv.DictReader(io.StringIO(z.read('Labels/turker_scores_full_interview.csv').decode('utf-8-sig'))))
        # This CSV has NO header: the first row is participant p1, not column names.
        transcripts = list(csv.reader(io.StringIO(z.read('Labels/interview_transcripts_by_turkers.csv').decode('utf-8-sig'))))
    ids = {r['id'] for r in records}
    aggregate_ids = {r['Participant'].lower() for r in scores if r['Worker'] == 'AGGR'}
    transcript_ids = {r[0].lower() for r in transcripts}
    participant_counts = Counter(r['participant'] for r in records)
    report = {
        'dataset': 'MIT Interview Dataset',
        'archive_sha256': {'Facial_Features.zip': sha256(features_zip), 'Labels.zip': sha256(labels_zip)},
        'crc_validation': 'passed for both archives',
        'feature_recordings': len(records), 'participants': len(participant_counts),
        'participants_with_two_recordings': sum(n == 2 for n in participant_counts.values()),
        'conditions': dict(Counter(r['condition'] for r in records)),
        'feature_rows_total': sum(r['rows'] for r in records),
        'feature_rows_range': [min(r['rows'] for r in records), max(r['rows'] for r in records)],
        'consistent_header': len(headers) == 1,
        'feature_columns': list(next(iter(headers))),
        'nonfinite_values': sum(r['nonfinite_values'] for r in records),
        'rows_with_nonfinite_values': sum(r['rows_with_nonfinite_values'] for r in records),
        'rows_with_nonfinite_fraction': sum(r['rows_with_nonfinite_values'] for r in records)
            / sum(r['rows'] for r in records),
        'recordings_with_nonfinite_values': sum(r['nonfinite_values'] > 0 for r in records),
        'per_recording_nonfinite_row_fraction_percentiles': dict(zip(['p0','p50','p95','p100'],
            np.percentile([r['rows_with_nonfinite_values'] / r['rows'] for r in records], [0,50,95,100]).tolist())),
        'all_zero_rows': sum(r['all_zero_rows'] for r in records),
        'pose_global_min': np.min([r['pose_min'] for r in records], axis=0).tolist(),
        'pose_global_max': np.max([r['pose_max'] for r in records], axis=0).tolist(),
        'rating_rows_including_aggregates': len(scores),
        'aggregate_rating_recordings': len(aggregate_ids),
        'transcript_recordings': len(transcript_ids), 'transcript_csv_has_header': False,
        'feature_ids_match_aggregate_ratings': ids == aggregate_ids,
        'feature_ids_match_transcripts': ids == transcript_ids,
        'rating_columns': list(scores[0]),
        'ai_assistance_labels': False,
        'condition_semantics': 'P=before career counseling; PP=after counseling. Neither is an AI-use label.',
        'feature_units': 'Not documented in supplied README. Do not assume Pitch/Yaw/Roll are degrees.',
        'timestamps_and_confidence': 'No explicit timestamp, face-presence, or tracking-confidence columns.',
        'transfer_readiness': 'Re-extract from raw video for the MediaPipe/MobileGaze model feature contract.',
        'governance': 'Research only; no redistribution; destroy original videos after research per supplied README.',
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / 'feature_audit.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    # Per-recording rows remain in the ignored local data directory.
    (out / 'recording_inventory.json').write_text(json.dumps(records, indent=2, allow_nan=False))
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('data/raw/video_research/mit'))
    p.add_argument('--out', type=Path, default=Path('data/processed/video_research/mit_transfer'))
    args = p.parse_args()
    audit(args.root / 'Facial_Features.zip', args.root / 'Labels.zip', args.out)
