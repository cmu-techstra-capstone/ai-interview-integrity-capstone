"""Local recorded-video -> measurements -> direction signals -> event timeline."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import cv2
import joblib
import numpy as np

from features import VisualMeasurements, events_from_rows


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def run(source: Path, model_path: Path, classifiers: Path, output: Path,
        sample_fps=5.0, minimum_event_s=2.0, max_seconds=None, gaze_model=None):
    if not np.isfinite(sample_fps) or not 0 < sample_fps <= 30 or minimum_event_s <= 0:
        raise ValueError('Invalid sampling/event settings')
    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or not np.isfinite(fps) or fps <= 0:
        raise ValueError('Unreadable video or invalid FPS: ' + str(source))
    effective_fps = min(sample_fps, fps)
    models = {task: joblib.load(classifiers / (task + '.joblib'))
              for task in ['head_deviation', 'eye_deviation']}
    detector = VisualMeasurements(model_path, video=True, gaze_model=gaze_model)
    rows = []
    frame_idx = sample_idx = 0
    started = time.perf_counter()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = frame_idx / fps
            frame_idx += 1
            if max_seconds is not None and t >= max_seconds:
                break
            if t + 1e-8 < sample_idx / effective_fps:
                continue
            sample_idx += 1
            clock = time.perf_counter()
            row = detector.measure(frame, round(t * 1000))
            for k in list(row):
                if k.startswith('pose_') or k.startswith('mobilegaze_'):
                    row['abs_' + k] = abs(row[k]) if row[k] is not None else None
            row['timestamp_s'] = t
            for task, bundle in models.items():
                row[task] = None
                row[task + '_score'] = None
                if (row['face_count'] != 1 or
                    (task == 'eye_deviation' and row['status'] != 'ok')):
                    continue
                if task == 'eye_deviation' and row.get('head_deviation') is not False:
                    continue
                values = [row.get(k) for k in bundle['features']]
                if any(v is None for v in values):
                    continue
                score = float(bundle['model'].predict_proba([values])[0, 1])
                row[task + '_score'] = score
                row[task] = bool(score >= bundle['threshold'])
            row['inference_ms'] = (time.perf_counter() - clock) * 1000
            rows.append(row)
    finally:
        cap.release()
        detector.close()
    if not rows:
        raise ValueError('No decoded frames')
    events = events_from_rows(rows, effective_fps, minimum_event_s)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'measurements.jsonl').open('w') as f:
        for row in rows:
            f.write(json.dumps(row, allow_nan=False) + '\n')
    total_s = min(frame_idx / fps, max_seconds) if max_seconds else frame_idx / fps
    summary = {'source_filename': source.name, 'source_sha256': file_hash(source),
               'source_fps': fps, 'sample_fps': effective_fps, 'sampled_frames': len(rows),
               'analyzed_seconds': total_s, 'elapsed_seconds': time.perf_counter() - started,
               'quality_status': dict(Counter(r['status'] for r in rows)),
               'median_inference_ms': float(np.median([r['inference_ms'] for r in rows])),
               'p95_inference_ms': float(np.percentile([r['inference_ms'] for r in rows], 95)),
               'minimum_event_seconds': minimum_event_s, 'events': events,
               'ai_assistance_probability': None,
               'interpretation': 'Direction/missing-detection events for review; no interview AI-use ground truth.',
               'face_loss_semantics': 'No face detected can be absence, occlusion, lighting, or detector failure.'}
    (output / 'timeline.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--model', type=Path, default=Path('data/models/video_research/face_landmarker.task'))
    p.add_argument('--classifiers', type=Path, default=Path('data/processed/video_research'))
    p.add_argument('--out', type=Path, default=Path('data/processed/video_research/demo'))
    p.add_argument('--sample-fps', type=float, default=5)
    p.add_argument('--min-event-seconds', type=float, default=2)
    p.add_argument('--max-seconds', type=float)
    p.add_argument('--gaze-model', type=Path)
    args = p.parse_args()
    result = run(args.source, args.model, args.classifiers, args.out,
                 args.sample_fps, args.min_event_seconds, args.max_seconds, args.gaze_model)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
