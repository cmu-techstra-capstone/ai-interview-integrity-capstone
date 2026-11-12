"""Frozen gaze model + one known center-gaze image per Columbia participant.

Calibration images are excluded from scoring. No classifier is fitted, and this
is an exploratory direction benchmark, not an interview/AI-use benchmark.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from relative_events import gaze_vector
from video_pipeline import file_hash


def five_point(rows):
    targets={(0,0),(-15,0),(15,0),(0,-10),(0,10)}
    labels=[];groups=[];scores={k:[] for k in ['forward','one_point','five_point_affine']}
    condition=[]
    for person in sorted({r['participant'] for r in rows}):
        subset=[r for r in rows if r['participant']==person]
        cal=[r for r in subset if (r['gaze_horizontal_deg'],r['gaze_vertical_deg']) in targets]
        x=np.array([[r['mobilegaze_yaw_deg'],r['mobilegaze_pitch_deg'],1] for r in cal])
        truth=np.array([[r['gaze_horizontal_deg'],r['gaze_vertical_deg']] for r in cal])
        if len(cal)!=5 or np.linalg.matrix_rank(x)<3:raise ValueError('Insufficient calibration geometry')
        coefficients=np.linalg.lstsq(x,truth,rcond=None)[0]
        condition.append(float(np.linalg.cond(x)))
        center=next(r for r in cal if r['gaze_horizontal_deg']==0 and r['gaze_vertical_deg']==0)
        baseline=np.array([center['mobilegaze_yaw_deg'],center['mobilegaze_pitch_deg']])
        for row in subset:
            if (row['gaze_horizontal_deg'],row['gaze_vertical_deg']) in targets:continue
            a=np.array([row['mobilegaze_yaw_deg'],row['mobilegaze_pitch_deg']])
            labels.append(row['label']);groups.append(person)
            scores['forward'].append(float(np.linalg.norm(a)))
            scores['one_point'].append(float(np.linalg.norm(a-baseline)))
            scores['five_point_affine'].append(float(np.linalg.norm(np.r_[a,1]@coefficients)))
    y=np.array(labels);g=np.array(groups);people=np.unique(g);rng=np.random.default_rng(20261029)
    scores={k:np.array(v) for k,v in scores.items()};delta=[]
    for _ in range(1000):
        ix=np.concatenate([np.flatnonzero(g==p) for p in rng.choice(people,len(people),replace=True)])
        delta.append(roc_auc_score(y[ix],scores['five_point_affine'][ix])-roc_auc_score(y[ix],scores['one_point'][ix]))
    return {'evaluated_images':len(y),'positive_images':int(y.sum()),'negative_images':int((y==0).sum()),
        'calibration_images_excluded':5*len(people),'participants':len(people),
        'calibration_targets_horizontal_vertical':sorted(targets),
        'score':'Euclidean magnitude in angle space; five-point method maps to target angles via per-person least squares.',
        'same_cohort_auroc':{k:float(roc_auc_score(y,v)) for k,v in scores.items()},
        'five_point_minus_one_point_paired_subject_bootstrap_95_interval':np.percentile(delta,[2.5,97.5]).tolist(),
        'at_10_degrees':{k:{'fpr':float(np.mean(v[y==0]>=10)),'recall':float(np.mean(v[y==1]>=10))} for k,v in scores.items()},
        'calibration_design_condition_number_range':[min(condition),max(condition)],
        'scope':'Known labeled calibration targets are allowed for enrollment and excluded from evaluation. Not available in MIT.'}


def main(path, model_name, out):
    rows=[json.loads(x) for x in path.read_text().splitlines()]
    calibration={r['participant']:r for r in rows
                 if r['gaze_vertical_deg']==0 and r['gaze_horizontal_deg']==0}
    labels=[];scores=[];raw_scores=[];groups=[]
    for r in rows:
        if r['gaze_vertical_deg']==0 and r['gaze_horizontal_deg']==0:continue
        if r['status']!='ok':continue
        center=calibration[r['participant']]
        v=gaze_vector([r['mobilegaze_yaw_deg'],r['mobilegaze_pitch_deg']])
        b=gaze_vector([center['mobilegaze_yaw_deg'],center['mobilegaze_pitch_deg']])
        labels.append(r['label']);groups.append(r['participant'])
        scores.append(float(np.degrees(np.arccos(np.clip(np.dot(v,b),-1,1)))))
        raw_scores.append(float(np.degrees(np.arccos(np.clip(v[2],-1,1)))))
    y=np.array(labels);s=np.array(scores);g=np.array(groups)
    people=np.unique(g);rng=np.random.default_rng(20261029);aucs=[]
    for _ in range(1000):
        ix=np.concatenate([np.flatnonzero(g==p) for p in rng.choice(people,len(people),replace=True)])
        aucs.append(roc_auc_score(y[ix],s[ix]))
    operating={}
    for threshold in [10,15,20,25]:
        pred=s>=threshold;fp=int(np.sum(pred & (y==0)));tp=int(np.sum(pred & (y==1)))
        operating[str(threshold)]={'false_positives':fp,'true_positives':tp,
            'fpr':fp/int(np.sum(y==0)),'recall':tp/int(np.sum(y==1))}
    report={'source':'Columbia Gaze Dataset frontal-head subset',
        'source_features_sha256':file_hash(path),'model':model_name+'; no Columbia classifier fit',
        'participants':len(people),'calibration_images_excluded':len(calibration),
        'evaluated_images':len(y),'positive_images':int(y.sum()),'negative_images':int((y==0).sum()),
        'positive_label':'abs horizontal>=10 degrees OR abs vertical>=10 degrees; gaze direction only',
        'raw_forward_distance_auroc_same_scored_cohort':float(roc_auc_score(y,raw_scores)),
        'relative_to_known_center_auroc':float(roc_auc_score(y,s)),
        'participant_bootstrap_95_interval':np.percentile(aucs,[2.5,97.5]).tolist(),
        'bootstrap_replicates':1000,'operating_points_degrees':operating,
        'calibration':'One known 0V/0H image per person; excluded from scored images.',
        'interpretation':'Exploratory calibrated direction scoring. MIT natural baseline is a different, unvalidated setup.',
        'comparison_note':'Different scored cohort from the 1,176-image trained-HGB benchmark; not a head-to-head ranking.',
        'ai_assistance_auroc':None,'five_point_exploration':five_point(rows)}
    out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--features',type=Path,default=Path('data/processed/video_research/columbia_features.jsonl'))
    p.add_argument('--model-name',default='Frozen Gaze360 MobileOne-S0 ONNX')
    p.add_argument('--out',type=Path,default=Path('data/processed/video_research/calibration_benchmark'))
    args=p.parse_args();main(args.features,args.model_name,args.out)
