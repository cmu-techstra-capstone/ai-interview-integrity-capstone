"""Paired participant-bootstrap comparison and alternating CPU inference timing."""
from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np
from sklearn.metrics import roc_auc_score

from features import MobileGaze
from relative_events import gaze_vector
from video_pipeline import file_hash


def score(path):
    rows=[json.loads(x) for x in path.read_text().splitlines()]
    centers={r['participant']:r for r in rows if r['gaze_vertical_deg']==0 and r['gaze_horizontal_deg']==0}
    results={}
    for r in rows:
        if r['gaze_vertical_deg']==0 and r['gaze_horizontal_deg']==0:continue
        c=centers[r['participant']]
        v=gaze_vector([r['mobilegaze_yaw_deg'],r['mobilegaze_pitch_deg']])
        b=gaze_vector([c['mobilegaze_yaw_deg'],c['mobilegaze_pitch_deg']])
        results[r['file']]={'label':r['label'],'person':r['participant'],
            'score':float(np.degrees(np.arccos(np.clip(np.dot(v,b),-1,1)))),'sha256':r['sha256']}
    return results


def main():
    root=Path('data/processed/video_research')
    paths={'mobileone_s0':root/'columbia_features.jsonl','resnet34':root/'columbia_resnet34.jsonl'}
    a=score(paths['mobileone_s0']);b=score(paths['resnet34'])
    if set(a)!=set(b):raise ValueError('Model cohorts differ')
    keys=sorted(a)
    for k in keys:
        if (a[k]['label'],a[k]['person'],a[k]['sha256'])!=(b[k]['label'],b[k]['person'],b[k]['sha256']):
            raise ValueError('Source/label mismatch')
    y=np.array([a[k]['label'] for k in keys]);g=np.array([a[k]['person'] for k in keys])
    sa=np.array([a[k]['score'] for k in keys]);sb=np.array([b[k]['score'] for k in keys])
    people=np.unique(g);rng=np.random.default_rng(20261029);deltas=[]
    for _ in range(1000):
        ix=np.concatenate([np.flatnonzero(g==p) for p in rng.choice(people,len(people),replace=True)])
        deltas.append(roc_auc_score(y[ix],sa[ix])-roc_auc_score(y[ix],sb[ix]))
    model_paths={name:Path('data/models/video_research')/(name+'_gaze.onnx') for name in paths}
    engines={name:MobileGaze(p) for name,p in model_paths.items()}
    # Synthetic image: isolates fixed-shape preprocessing + CNN, no face detector or I/O.
    image=np.zeros((448,448,3),dtype=np.uint8)
    for _ in range(5):
        for m in engines.values():m.measure(image)
    timing={name:[] for name in engines}
    for i in range(30):
        order=list(engines) if i%2==0 else list(engines)[::-1]
        for name in order:
            start=time.perf_counter();engines[name].measure(image)
            timing[name].append((time.perf_counter()-start)*1000)
    report={'scored_images':len(keys),'participants':len(people),
        'matched_image_and_label_hash_check':'passed',
        'one_point_auc':{'mobileone_s0':float(roc_auc_score(y,sa)),'resnet34':float(roc_auc_score(y,sb))},
        'mobileone_minus_resnet_auc':float(roc_auc_score(y,sa)-roc_auc_score(y,sb)),
        'paired_participant_bootstrap_95_delta':np.percentile(deltas,[2.5,97.5]).tolist(),
        'bootstrap_replicates':1000,
        'weight_metadata':{name:{'sha256':file_hash(p),'bytes':p.stat().st_size} for name,p in model_paths.items()},
        'cpu_microbenchmark':{name:{'input_shape':engine.input.shape,'median_ms':float(np.median(timing[name])),
            'p95_ms':float(np.percentile(timing[name],95))} for name,engine in engines.items()},
        'timing_scope':'30 alternating trials after 5 warmups per model, synthetic 448px BGR input, CPUExecutionProvider, 2 intra-op threads. MIT jobs ran concurrently; not an isolated or end-to-end latency estimate.',
        'scope':'Exploratory direction comparison; no interview AI-use labels.',
        'source_feature_sha256':{name:file_hash(p) for name,p in paths.items()}}
    out=root/'calibrated_model_comparison.json';out.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
