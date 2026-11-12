"""Exploratory within-recording pose/gaze changes, not AI-use classification.

MIT uses an oblique third-person camera. A natural first-30-second baseline is an
experimental adaptation, not a verified camera/screen calibration instruction.
All thresholds describe estimated angular change and need event annotations.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from features import events_from_rows
from video_pipeline import file_hash

POSE = ['pose_x_deg', 'pose_y_deg', 'pose_z_deg']
GAZE = ['mobilegaze_yaw_deg', 'mobilegaze_pitch_deg']


def finite_values(row, keys):
    return row.get('face_count') == 1 and all(
        row.get(k) is not None and np.isfinite(row[k]) for k in keys)


def rotation_medoid(values):
    rotations = Rotation.from_euler('xyz', values, degrees=True)
    totals = [np.sum((r.inv() * rotations).magnitude()) for r in rotations]
    return rotations[int(np.argmin(totals))]


def gaze_vector(values):
    yaw, pitch = np.radians(values)
    return np.array([np.cos(pitch) * np.sin(yaw), np.sin(pitch), np.cos(pitch) * np.cos(yaw)])


def analyze(rows, sample_fps, analyzed_seconds, calibration_seconds=30, angle_degrees=15, min_samples=10):
    calibration = [r for r in rows if r['timestamp_s'] < calibration_seconds]
    head_calibration = [r for r in calibration if finite_values(r, POSE)]
    baseline = rotation_medoid([[r[k] for k in POSE] for r in head_calibration]) if len(head_calibration) >= min_samples else None
    head_angles={}
    if baseline is not None:
        valid=[r for r in rows if finite_values(r, POSE)]
        if valid:
            rotations=Rotation.from_euler('xyz',[[r[k] for k in POSE] for r in valid],degrees=True)
            angles=np.degrees((baseline.inv()*rotations).magnitude())
            head_angles={id(r):float(v) for r,v in zip(valid,angles)}
    def head_angle(row):
        return head_angles.get(id(row))
    eye_calibration = [r for r in calibration if r['status'] == 'ok' and finite_values(r, GAZE)
                       and head_angle(r) is not None and head_angle(r) < 15]
    gaze_baseline = None
    if len(eye_calibration) >= min_samples:
        directions = np.array([gaze_vector([r[k] for k in GAZE]) for r in eye_calibration])
        direction = np.median(directions, axis=0)
        if np.linalg.norm(direction) > 1e-9: gaze_baseline = direction / np.linalg.norm(direction)
    evaluated = []
    for original in rows:
        if original['timestamp_s'] < calibration_seconds: continue
        row = {k: original[k] for k in ['timestamp_s','status']}
        row.update(head_deviation=None, eye_deviation=None, relative_head_angle_deg=None, relative_gaze_angle_deg=None)
        head = head_angle(original)
        if head is not None:
            row['relative_head_angle_deg'] = head
            row['head_deviation'] = bool(head >= angle_degrees)
        if gaze_baseline is not None and row['head_deviation'] is False and original['status'] == 'ok' and finite_values(original, GAZE):
            direction = gaze_vector([original[k] for k in GAZE])
            angle = float(np.degrees(np.arccos(np.clip(np.dot(direction, gaze_baseline), -1, 1))))
            row['relative_gaze_angle_deg'] = angle
            row['eye_deviation'] = bool(angle >= angle_degrees)
        evaluated.append(row)
    events = events_from_rows(evaluated, sample_fps, 2)
    mapping = {'head_deviation':'relative_head_change','eye_deviation':'relative_gaze_change'}
    for event in events:
        event['type'] = mapping.get(event['type'], event['type'])
        event['end_s'] = min(event['end_s'], analyzed_seconds)
        event['duration_s'] = round(event['end_s'] - event['start_s'], 3)
    events = [e for e in events if e['duration_s'] >= 2 - 1e-8]
    comparison = {}
    original_eval = [r for r in rows if r['timestamp_s'] >= calibration_seconds]
    for task in ['head_deviation','eye_deviation']:
        common = [(a,b) for a,b in zip(original_eval,evaluated) if a.get(task) is not None and b.get(task) is not None]
        comparison[task] = {'common_measured_frames':len(common),
            'absolute_positive_frames':sum(a[task] is True for a,b in common),
            'relative_positive_frames':sum(b[task] is True for a,b in common)}
    summary = {
        'calibration_seconds':calibration_seconds, 'minimum_calibration_samples':min_samples,
        'angle_change_threshold_degrees':angle_degrees, 'minimum_event_seconds':2,
        'head_calibration_samples':len(head_calibration), 'gaze_calibration_samples':len(eye_calibration),
        'head_baseline_available':baseline is not None,'gaze_baseline_available':gaze_baseline is not None,
        'evaluation_seconds':max(0,analyzed_seconds-calibration_seconds), 'evaluation_frames':len(evaluated),
        'signal_coverage':{task:{'measured_frames':sum(r[task] is not None for r in evaluated),
            'positive_frames':sum(r[task] is True for r in evaluated)} for task in ['head_deviation','eye_deviation']},
        'absolute_signal_coverage_same_evaluation_period':{task:{
            'measured_frames':sum(r.get(task) is not None for r in original_eval),
            'positive_frames':sum(r.get(task) is True for r in original_eval)}
            for task in ['head_deviation','eye_deviation']},
        'absolute_relative_common_frame_comparison':comparison, 'events':events,
        'ai_assistance_probability':None,
        'interpretation':'Angular changes relative to an unlabeled natural baseline; observed events, not cheating labels.'}
    return summary, evaluated


def batch(root, out, calibration_seconds=30, allow_partial=False):
    inventory = json.loads((root/'inventory.json').read_text())
    out.mkdir(parents=True,exist_ok=True)
    records=[]
    sensitivity={str(t):Counter() for t in [10,15,20,25]}
    code_hash=file_hash(Path(__file__))
    for item in inventory['videos']:
        source=root/item['recording_id']; dest=out/item['recording_id']
        if not (source/'timeline.json').exists() or not (source/'measurements.jsonl').exists():
            if allow_partial:continue
            raise ValueError('Source batch incomplete; use --allow-partial only for progress analysis.')
        try:
            summary=json.loads((source/'timeline.json').read_text())
        except json.JSONDecodeError:
            if allow_partial:continue
            raise
        if 'batch_config_sha256' not in summary:
            if allow_partial:continue
            raise ValueError('Source recording has not completed batch finalization.')
        source_hash=file_hash(source/'measurements.jsonl')
        cached=json.loads((dest/'timeline.json').read_text()) if (dest/'timeline.json').exists() else None
        if (cached and cached.get('source_measurements_sha256')==source_hash
            and cached.get('relative_code_sha256')==code_hash and cached.get('calibration_seconds')==calibration_seconds
            and 'threshold_sensitivity_event_counts' in cached and (dest/'measurements.jsonl').exists()):
            results=cached
        else:
            rows=[json.loads(line) for line in (source/'measurements.jsonl').read_text().splitlines()]
            results,measurements=analyze(rows,summary['sample_fps'],summary['analyzed_seconds'],calibration_seconds)
            results['source_measurements_sha256']=source_hash
            results['relative_code_sha256']=code_hash
            results['batch_config_sha256']=summary['batch_config_sha256']
            results['threshold_sensitivity_event_counts']={}
            for angle in [10,15,20,25]:
                variant=results if angle==15 else analyze(rows,summary['sample_fps'],summary['analyzed_seconds'],calibration_seconds,angle)[0]
                results['threshold_sensitivity_event_counts'][str(angle)]=dict(Counter(e['type'] for e in variant['events']))
            dest.mkdir(parents=True,exist_ok=True)
            (dest/'timeline.json').write_text(json.dumps(results,indent=2,allow_nan=False))
            (dest/'measurements.jsonl').write_text('\n'.join(json.dumps(r,allow_nan=False) for r in measurements)+'\n')
        records.append(results)
        for angle,counts in results['threshold_sensitivity_event_counts'].items():sensitivity[angle].update(counts)
    signals={task:Counter() for task in ['head_deviation','eye_deviation']}
    common={task:Counter() for task in signals}
    absolute={task:Counter() for task in signals}
    counts=Counter()
    durations={}
    for r in records:
        counts.update(e['type'] for e in r['events'])
        for event in r['events']:durations.setdefault(event['type'],[]).append(event['duration_s'])
        for task in signals:
            signals[task].update(r['signal_coverage'][task])
            absolute[task].update(r['absolute_signal_coverage_same_evaluation_period'][task])
            common[task].update(r['absolute_relative_common_frame_comparison'][task])
    seconds=sum(r['evaluation_seconds'] for r in records); frames=sum(r['evaluation_frames'] for r in records)
    report={'recordings':len(records),'expected_recordings':len(inventory['videos']),
        'partial':len(records)!=len(inventory['videos']),
        'evaluation_seconds':seconds,'evaluation_frames':frames,
        'calibration_seconds_per_recording':calibration_seconds,
        'recordings_with_head_baseline':sum(r['head_baseline_available'] for r in records),
        'recordings_with_gaze_baseline':sum(r['gaze_baseline_available'] for r in records),
        'signal_coverage':{k:{**v,'measured_fraction':v['measured_frames']/frames if frames else None,
            'positive_fraction_of_measured':v['positive_frames']/v['measured_frames'] if v['measured_frames'] else None} for k,v in signals.items()},
        'absolute_signal_coverage_same_evaluation_period':{k:{**v,
            'measured_fraction':v['measured_frames']/frames if frames else None,
            'positive_fraction_of_measured':v['positive_frames']/v['measured_frames'] if v['measured_frames'] else None}
            for k,v in absolute.items()},
        'absolute_relative_common_frame_comparison':{k:dict(v) for k,v in common.items()},
        'event_counts':dict(counts),'events_per_minute':{k:v/(seconds/60) for k,v in counts.items()} if seconds else {},
        'event_duration_summary':{k:{'median_seconds':float(np.median(v)),
            'p95_seconds':float(np.percentile(v,95)),'maximum_seconds':max(v),
            'events_at_least_4_seconds':sum(x>=4 for x in v),
            'events_at_least_6_seconds':sum(x>=6 for x in v)} for k,v in durations.items()},
        'angle_threshold_sensitivity_event_counts':{k:dict(v) for k,v in sensitivity.items()},
        'fixed_primary_angle_degrees':15,'sample_fps':inventory['settings']['sample_fps'],
        'ai_assistance_auroc':None,'event_false_positive_rate':None,
        'scope':'Exploratory natural baseline after absolute-model failure in pilot; no directed calibration or event/AI-use ground truth.',
        'privacy':'Per-recording features/timelines are local only; publish aggregate report only.'}
    (out/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--calibration-seconds',type=float,default=30)
    p.add_argument('--allow-partial',action='store_true')
    args=p.parse_args()
    if not np.isfinite(args.calibration_seconds) or args.calibration_seconds<=0:p.error('Positive finite calibration duration required.')
    batch(args.root,args.out,args.calibration_seconds,args.allow_partial)
