"""Larger eye-only component benchmark and transfer of the 3-person prototype."""
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
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from benchmark import metrics
from compare_gaze import augment
from features import ALL_FEATURES, GAZE_FEATURES, VisualMeasurements

ROOT = Path('data/processed/video_research')


def extract():
    raw = Path('data/raw/video_research/columbia')
    manifest = json.loads((raw / 'manifest.json').read_text())
    model = VisualMeasurements(Path('data/models/video_research/face_landmarker.task'),
                               gaze_model=Path('data/models/video_research/mobileone_s0_gaze.onnx'))
    try:
        with (ROOT / 'columbia_features.jsonl').open('w') as out:
            for i, item in enumerate(manifest['records']):
                path = raw / item['file']
                if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                    raise ValueError('Source changed')
                frame = cv2.imread(str(path))
                if frame is None: raise ValueError('Decode failed')
                start = time.perf_counter(); row = model.measure(frame)
                row['measurement_ms'] = 1000 * (time.perf_counter()-start)
                row.update(item)
                row['label'] = int(abs(item['gaze_horizontal_deg']) >= 10 or abs(item['gaze_vertical_deg']) >= 10)
                out.write(json.dumps(row,allow_nan=False)+'\n')
                if (i+1)%100==0: print(f'Columbia {i+1}/1176 measured',flush=True)
    finally: model.close()


def train():
    allrows = [augment(json.loads(s)) for s in (ROOT / 'columbia_features.jsonl').read_text().splitlines()]
    needed = ALL_FEATURES + GAZE_FEATURES
    rows = [r for r in allrows if r['status']=='ok' and all(r.get(k) is not None for k in needed)]
    y = np.array([r['label'] for r in rows]); groups=np.array([r['participant'] for r in rows])
    result={'dataset':'Columbia frontal-head 21-target subset', 'source_frames':len(allrows),
            'eligible_frames':len(rows), 'coverage':len(rows)/len(allrows),
            'participants':len(set(groups)), 'quality_status':dict(Counter(r['status'] for r in allrows)),
            'task':'gaze target >=10 degrees vs central -5/0/+5 horizontal at zero vertical; head pose fixed zero',
            'grouping':'5 folds, disjoint participants, shuffled group order with seed 42',
            'variants':{}, 'ai_assistance_evaluated':False}
    splits=list(GroupKFold(5,shuffle=True,random_state=42).split(np.zeros(len(y)),y,groups))
    variants={'iris_geometry': ALL_FEATURES,
              'mobilegaze': GAZE_FEATURES+['abs_'+k for k in GAZE_FEATURES],
              'combined': ALL_FEATURES+GAZE_FEATURES+['abs_'+k for k in GAZE_FEATURES]}
    models={'logistic':make_pipeline(StandardScaler(),LogisticRegression(C=1,class_weight='balanced',max_iter=2000,random_state=42)),
            'hist_gradient_boosting':HistGradientBoostingClassifier(max_iter=150,max_depth=3,l2_regularization=1,learning_rate=.05,random_state=42)}
    for vname,fs in variants.items():
        x=np.array([[r[k] for k in fs] for r in rows])
        for mname,est in models.items():
            scores=np.zeros(len(y));folds=[]
            for train,test in splits:
                assert not set(groups[train])&set(groups[test])
                clf=clone(est).fit(x[train],y[train]);s=clf.predict_proba(x[test])[:,1];scores[test]=s
                folds.append({'held_out_participants':sorted(set(groups[test])), **metrics(y[test],s)})
            key=vname+'/'+mname;result['variants'][key]={'pooled_oof':metrics(y,scores),'folds':folds}
            print(key,result['variants'][key]['pooled_oof'],flush=True)
            if vname=='mobilegaze' and mname=='logistic':
                shuffled=np.random.default_rng(42).permutation(y);ss=np.zeros(len(y))
                for train,test in splits:
                    c=clone(est).fit(x[train],shuffled[train]);ss[test]=c.predict_proba(x[test])[:,1]
                result['shuffled_label_control']=metrics(shuffled,ss)
                joblib.dump({'model':clone(est).fit(x,y),'features':fs,'threshold':.5,
                             'scope':'Columbia target deviation; only centered-head images validated'}, ROOT/'columbia_eye_deviation.joblib')
    # No Columbia fitting in this transfer condition.
    source=joblib.load(ROOT/'phase2/eye_deviation.joblib')
    x=np.array([[r[k] for k in source['features']] for r in rows])
    result['CSD_trained_model_external_Columbia_test']=metrics(y,source['model'].predict_proba(x)[:,1])
    result['median_measurement_ms']=float(np.median([r['measurement_ms'] for r in allrows]))
    result['p95_measurement_ms']=float(np.percentile([r['measurement_ms'] for r in allrows],95))
    (ROOT/'columbia_metrics.json').write_text(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['extract','train']);args=p.parse_args()
    extract() if args.mode=='extract' else train()
