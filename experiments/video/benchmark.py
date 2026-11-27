"""Frozen-subset measurements and participant-separated component experiments."""
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
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (balanced_accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import LeaveOneGroupOut, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from features import ALL_FEATURES, HEAD_FEATURES, VisualMeasurements, annotation


def metrics(y, score):
    pred = np.asarray(score) >= .5
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {'n': len(y), 'positives': int(np.sum(y)),
            'auroc': float(roc_auc_score(y, score)) if len(set(y)) == 2 else None,
            'balanced_accuracy': float(balanced_accuracy_score(y, pred)),
            'precision': float(precision_score(y, pred, zero_division=0)),
            'recall': float(recall_score(y, pred, zero_division=0)),
            'f1': float(f1_score(y, pred, zero_division=0)),
            'fpr': float(fp / (tn + fp)) if tn + fp else None,
            'confusion': {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)}}


def extract(root, model, out, gaze_model=None):
    source = root / 'scenarios'
    index = json.loads((root / 'scenario_subset.json').read_text())
    images = [x for x in index['files'] if x['filename'].endswith('.jpg')]
    detector = VisualMeasurements(model, gaze_model=gaze_model)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open('w') as f:
            for i, item in enumerate(images):
                path = source / item['filename']
                if hashlib.sha256(path.read_bytes()).hexdigest() != item['content_details']['sha256_hash']:
                    raise ValueError('Image hash mismatch: ' + path.name)
                frame = cv2.imread(str(path))
                if frame is None:
                    raise ValueError('Decode failed: ' + path.name)
                t = time.perf_counter()
                row = detector.measure(frame)
                row['measurement_ms'] = (time.perf_counter() - t) * 1000
                row.update(annotation(path.with_suffix('.txt')))
                row.update({'file': path.name, 'participant': path.stem[:2],
                            'sequence': path.stem.split('_')[0],
                            'source_sha256': item['content_details']['sha256_hash']})
                f.write(json.dumps(row, allow_nan=False) + '\n')
                if (i + 1) % 100 == 0:
                    print(f'measured {i+1}/{len(images)}', flush=True)
    finally:
        detector.close()


def evaluate(rows, output):
    models = {
        'majority': DummyClassifier(strategy='most_frequent'),
        'logistic': make_pipeline(StandardScaler(), LogisticRegression(C=1, class_weight='balanced', max_iter=2000, random_state=42)),
        'hist_gradient_boosting': HistGradientBoostingClassifier(max_iter=150, max_depth=3, l2_regularization=1, learning_rate=.05, random_state=42)}
    result = {'source_frames': len(rows), 'participants': dict(Counter(r['participant'] for r in rows)),
              'quality_status': dict(Counter(r['status'] for r in rows)),
              'median_measurement_ms': float(np.median([r['measurement_ms'] for r in rows])),
              'p95_measurement_ms': float(np.percentile([r['measurement_ms'] for r in rows], 95)),
              'tasks': {}, 'ai_assistance_evaluated': False}
    output.mkdir(parents=True, exist_ok=True)
    for task in ['head_deviation', 'eye_deviation', 'eye_deviation_when_head_centered']:
        is_head = task == 'head_deviation'
        label = 'head_label' if is_head else 'eye_label'
        center = 3 if is_head else 8
        features = HEAD_FEATURES if is_head else ALL_FEATURES
        selected = [r for r in rows if r[label] is not None
                    and all(r.get(k) is not None for k in features)
                    and (is_head or r['status'] == 'ok')
                    and (not task.endswith('when_head_centered') or r['head_label'] == 3)]
        x = np.array([[r[k] for k in features] for r in selected])
        y = np.array([int(r[label] != center) for r in selected])
        groups = np.array([r['participant'] for r in selected])
        tr = {'coverage_of_all_frames': len(selected) / len(rows), 'eligible_frames': len(selected),
              'features': features, 'classes': dict(Counter(str(r[label]) for r in selected)), 'models': {}}
        splits = list(LeaveOneGroupOut().split(x, y, groups))
        for name, estimator in models.items():
            scores = np.full(len(y), np.nan)
            folds = []
            for train, test in splits:
                assert not set(groups[train]) & set(groups[test])
                clf = clone(estimator).fit(x[train], y[train])
                score = clf.predict_proba(x[test])[:, list(clf.classes_).index(1)]
                scores[test] = score
                folds.append({'held_out_participant': str(groups[test[0]]), **metrics(y[test], score)})
            tr['models'][name] = {'participant_folds': folds, 'pooled_oof': metrics(y, scores)}
        # Diagnostic only: adjacent frames of the same people leak across this split.
        train, test = train_test_split(np.arange(len(y)), test_size=.25, stratify=y, random_state=42)
        clf = clone(models['logistic']).fit(x[train], y[train])
        tr['random_frame_split_DIAGNOSTIC_ONLY'] = metrics(y[test], clf.predict_proba(x[test])[:, 1])
        shuffled = np.random.default_rng(42).permutation(y)
        score = np.zeros(len(y))
        for train, test in splits:
            clf = clone(models['logistic']).fit(x[train], shuffled[train])
            score[test] = clf.predict_proba(x[test])[:, 1]
        tr['shuffled_label_control'] = metrics(shuffled, score)
        # Fixed model family; export for a local engineering demo, not independent validation.
        if not task.endswith('when_head_centered'):
            fitted = clone(models['logistic']).fit(x, y)
            joblib.dump({'model': fitted, 'features': features, 'task': task,
                         'scope': 'scripted direction classes, no AI-use probability',
                         'participants': sorted(set(groups)), 'threshold': .5}, output / (task + '.joblib'))
        result['tasks'][task] = tr
    (output / 'component_metrics.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({t: {m: v['pooled_oof'] for m, v in d['models'].items()}
                      for t, d in result['tasks'].items()}, indent=2), flush=True)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['extract', 'train'])
    p.add_argument('--root', type=Path, default=Path('data/raw/video_research'))
    p.add_argument('--model', type=Path, default=Path('data/models/video_research/face_landmarker.task'))
    p.add_argument('--features', type=Path, default=Path('data/processed/video_research/frame_features.jsonl'))
    p.add_argument('--out', type=Path, default=Path('data/processed/video_research'))
    p.add_argument('--gaze-model', type=Path)
    args = p.parse_args()
    if args.mode == 'extract':
        extract(args.root, args.model, args.features, args.gaze_model)
    else:
        evaluate([json.loads(s) for s in args.features.read_text().splitlines()], args.out)


if __name__ == '__main__':
    main()
