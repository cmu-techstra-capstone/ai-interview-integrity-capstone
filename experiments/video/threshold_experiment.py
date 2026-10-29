"""Participant-nested threshold selection. Outer test labels never choose a cutoff."""
import json
import hashlib
from pathlib import Path

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
from features import ALL_FEATURES, GAZE_FEATURES

ROOT=Path('data/processed/video_research')
FEATURES=ALL_FEATURES+GAZE_FEATURES+['abs_'+k for k in GAZE_FEATURES]


def train_threshold(model,x,y,g,target=.10):
    scores=np.zeros(len(y))
    for a,b in GroupKFold(3,shuffle=True,random_state=24).split(x,y,g):
        assert not set(g[a])&set(g[b])
        scores[b]=clone(model).fit(x[a],y[a]).predict_proba(x[b])[:,1]
    # Strictly above the selected quantile so ties cannot inflate the target FPR.
    return float(np.nextafter(np.quantile(scores[y==0],1-target,method='higher'),np.inf))


def group_bootstrap(y,raw,pred,g):
    rng=np.random.default_rng(20261029);groups=np.unique(g);values=[]
    for _ in range(1000):
        ids=np.concatenate([np.where(g==who)[0] for who in rng.choice(groups,len(groups),replace=True)])
        m=metrics(y[ids],pred[ids]);m['auroc']=metrics(y[ids],raw[ids])['auroc'];values.append(m)
    return {k:list(map(float,np.quantile([v[k] for v in values],[.025,.975]))) for k in ['auroc','fpr','recall']}


def main():
    rows=[augment(json.loads(s)) for s in (ROOT/'columbia_features.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['status']=='ok' and all(r.get(k) is not None for k in FEATURES)]
    x=np.array([[r[k] for k in FEATURES] for r in rows]);y=np.array([r['label'] for r in rows]);g=np.array([r['participant'] for r in rows])
    models={'combined_logistic':make_pipeline(StandardScaler(),LogisticRegression(C=1,class_weight='balanced',max_iter=2000,random_state=42)),
            'combined_balanced_HGB':HistGradientBoostingClassifier(max_iter=150,max_depth=3,l2_regularization=1,learning_rate=.05,class_weight='balanced',random_state=42)}
    result={'protocol':'5 outer participant folds; threshold chosen from 3 inner participant folds within each training fold only',
            'feature_file_sha256':hashlib.sha256((ROOT/'columbia_features.jsonl').read_bytes()).hexdigest(),
            'nominal_training_FPR_target':.1,'features':FEATURES,'models':{},
            'interpretation':'Exploratory follow-up on the same cohort; independent final interview validation still required.'}
    for name,model in models.items():
        predictions=np.zeros(len(y)); raw=np.zeros(len(y));folds=[]
        for a,b in GroupKFold(5,shuffle=True,random_state=42).split(x,y,g):
            threshold=train_threshold(model,x[a],y[a],g[a])
            clf=clone(model).fit(x[a],y[a]);s=clf.predict_proba(x[b])[:,1]
            raw[b]=s;predictions[b]=(s>=threshold).astype(float)
            m=metrics(y[b],predictions[b]);m['auroc']=metrics(y[b],s)['auroc']
            folds.append({'participants':sorted(set(g[b])),'inner_chosen_threshold':threshold,**m})
        combined=metrics(y,predictions);combined['auroc']=metrics(y,raw)['auroc']
        result['models'][name]={'pooled_oof':combined,'folds':folds,
                               'participant_bootstrap_95_percent':group_bootstrap(y,raw,predictions,g),
                               'bootstrap_scope':'1000 resamples of participant groups in fixed OOF predictions; models not refitted'}
        print(name,combined,flush=True)
        if name=='combined_balanced_HGB':
            threshold=train_threshold(model,x,y,g)
            joblib.dump({'model':clone(model).fit(x,y),'features':FEATURES,'threshold':threshold,
                         'scope':'Columbia gaze-target proxy, centered-head domain, experimental review cue'}, ROOT/'columbia_eye_review.joblib')
            result['exported_threshold']=threshold
            (ROOT/'phase3').mkdir(exist_ok=True)
            joblib.dump(joblib.load(ROOT/'phase2/head_deviation.joblib'),ROOT/'phase3/head_deviation.joblib')
            joblib.dump(joblib.load(ROOT/'columbia_eye_review.joblib'),ROOT/'phase3/eye_deviation.joblib')
    (ROOT/'nested_threshold_metrics.json').write_text(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':main()
