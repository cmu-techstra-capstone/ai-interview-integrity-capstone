"""Exploratory second iteration after the baseline exposed eye-only failure."""
import json
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from benchmark import metrics
from features import ALL_FEATURES, EYE_FEATURES, GAZE_FEATURES, HEAD_FEATURES

ROOT = Path('data/processed/video_research')


def augment(row):
    row = dict(row)
    for k in HEAD_FEATURES + GAZE_FEATURES:
        row['abs_' + k] = abs(row[k]) if row.get(k) is not None else None
    return row


def main():
    rows = [augment(json.loads(s)) for s in (ROOT / 'frame_features_gaze.jsonl').read_text().splitlines()]
    estimators = {
        'logistic': make_pipeline(StandardScaler(), LogisticRegression(C=1, class_weight='balanced', max_iter=2000, random_state=42)),
        'hist_gradient_boosting': HistGradientBoostingClassifier(max_iter=150, max_depth=3, l2_regularization=1, learning_rate=.05, random_state=42)}
    variants = {
        'head_absolute_geometry': HEAD_FEATURES + ['abs_' + k for k in HEAD_FEATURES],
        'iris_geometry': ALL_FEATURES,
        'iris_only': EYE_FEATURES,
        'mobilegaze': GAZE_FEATURES + ['abs_' + k for k in GAZE_FEATURES],
        'combined': ALL_FEATURES + GAZE_FEATURES + ['abs_' + k for k in GAZE_FEATURES + HEAD_FEATURES]}
    result = {'iteration': 'exploratory, after observing baseline failure; not a new untouched test set',
              'model_training': 'pretrained face mesh / pretrained Gaze360 MobileOne; own direction classifiers',
              'tasks': {}}
    start = time.perf_counter()
    for task in ['head_deviation', 'eye_deviation', 'eye_deviation_when_head_centered']:
        head = task == 'head_deviation'
        candidates = {'head_absolute_geometry': variants['head_absolute_geometry']} if head else {k:v for k,v in variants.items() if k != 'head_absolute_geometry'}
        needed = sorted({f for fs in candidates.values() for f in fs})
        selected = [r for r in rows if r['head_label' if head else 'eye_label'] is not None
                    and (head or r['status'] == 'ok')
                    and all(r.get(k) is not None for k in needed)
                    and (not task.endswith('when_head_centered') or r['head_label'] == 3)]
        label = np.array([int(r['head_label' if head else 'eye_label'] != (3 if head else 8)) for r in selected])
        groups = np.array([r['participant'] for r in selected])
        splits = list(LeaveOneGroupOut().split(np.zeros(len(label)), label, groups))
        result['tasks'][task] = {'n': len(label), 'coverage': len(label) / len(rows), 'variants': {}}
        for vname, fs in candidates.items():
            x = np.array([[r[f] for f in fs] for r in selected])
            for mname, estimator in estimators.items():
                scores = np.zeros(len(label)); folds = []
                for train, test in splits:
                    assert not set(groups[train]) & set(groups[test])
                    clf = clone(estimator).fit(x[train], label[train])
                    score = clf.predict_proba(x[test])[:, 1]
                    scores[test] = score
                    folds.append({'participant': str(groups[test[0]]), **metrics(label[test], score)})
                name = vname + '/' + mname
                result['tasks'][task]['variants'][name] = {'pooled_oof': metrics(label, scores), 'folds': folds, 'features': fs}
                # Export exploratory LR candidates. Eye model applies only when head is centered.
                if mname == 'logistic' and ((head and vname == 'head_absolute_geometry') or (task == 'eye_deviation_when_head_centered' and vname == 'mobilegaze')):
                    artifact = {'model': clone(estimator).fit(x, label), 'features': fs, 'task': task,
                                'threshold': .5, 'scope': 'scripted direction classification, no AI-use probability'}
                    export_task = 'head_deviation' if head else 'eye_deviation'
                    joblib.dump(artifact, ROOT / 'phase2' / (export_task + '.joblib'))
        print(task, {k:round(v['pooled_oof']['auroc'],4) for k,v in result['tasks'][task]['variants'].items()}, flush=True)
    result['training_seconds'] = time.perf_counter() - start
    result['median_measurement_with_gaze_ms'] = float(np.median([r['measurement_ms'] for r in rows]))
    result['p95_measurement_with_gaze_ms'] = float(np.percentile([r['measurement_ms'] for r in rows],95))
    (ROOT / 'gaze_comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False))


if __name__ == '__main__':
    (ROOT / 'phase2').mkdir(exist_ok=True)
    main()
