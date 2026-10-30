"""Unlabeled interview-domain transfer checks; resumable, local artifacts only.

Flag rates measure pipeline behavior, not false-positive rates or AI-use accuracy.
Use --probe-only before inference to verify source layout and recording duration.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import subprocess

from video_pipeline import file_hash, run

MEDIA = {'.mp4', '.avi', '.wmv', '.mov', '.mkv', '.webm', '.m4v'}


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
        'format=duration:stream=codec_type,width,height,avg_frame_rate', '-of', 'json', str(path)],
        capture_output=True, text=True, timeout=45, check=True)
    data = json.loads(result.stdout)
    return {'size_bytes': path.stat().st_size, 'duration_s': float(data['format'].get('duration', 0)),
            'streams': data.get('streams', [])}


def aggregate(summaries):
    quality = Counter(); events = Counter(); duration = 0; samples = 0
    signals = {task: Counter() for task in ['head_deviation', 'eye_deviation']}
    elapsed = 0
    for r in summaries:
        quality.update(r['quality_status']); samples += r['sampled_frames']
        duration += r['analyzed_seconds']; events.update(e['type'] for e in r['events'])
        elapsed += r['elapsed_seconds']
        for task in signals:
            signals[task].update(r.get('signal_coverage', {}).get(task, {}))
    return {'recordings': len(summaries), 'analyzed_seconds': duration,
        'sampled_frames': samples, 'quality_counts': dict(quality),
        'eye_image_quality_pass_fraction': quality['ok'] / samples if samples else None,
        'signal_coverage': {task: {**counts,
            'measured_fraction': counts['measured_frames'] / samples if samples else None,
            'positive_fraction_of_measured': counts['positive_frames'] / counts['measured_frames']
                if counts['measured_frames'] else None} for task,counts in signals.items()},
        'pipeline_elapsed_seconds': elapsed,
        'processing_seconds_per_video_second': elapsed / duration if duration else None,
        'event_counts': dict(events),
        'events_per_recording_minute': {k:v / (duration / 60) for k,v in events.items()} if duration else {},
        'event_rate_semantics': 'Observed flag rates only; no manual event ground truth supplied.',
        'false_positive_rate': None, 'ai_assistance_auroc': None}


def process_one(path, item, output_root, fingerprint, sample_fps, max_seconds):
    out=output_root/item['recording_id']; old=out/'timeline.json'
    try:
        cached=json.loads(old.read_text()) if old.exists() else None
        if cached and cached.get('batch_config_sha256')==fingerprint and cached.get('source_sha256')==file_hash(path):
            r=cached
        else:
            r=run(path,Path('data/models/video_research/face_landmarker.task'),
                  Path('data/processed/video_research/phase3'),out,sample_fps,2,max_seconds,
                  Path('data/models/video_research/mobileone_s0_gaze.onnx'))
            r['batch_config_sha256']=fingerprint
            old.write_text(json.dumps(r,indent=2))
        return item['recording_id'],r,None
    except Exception as e:
        return item['recording_id'],None,str(e)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source_root', type=Path)
    p.add_argument('--out', type=Path, default=Path('data/processed/video_research/mit_transfer'))
    p.add_argument('--limit', type=int)
    p.add_argument('--include-stems', nargs='+', help='Explicit recording stems; selection recorded in inventory.')
    p.add_argument('--max-seconds', type=float)
    p.add_argument('--sample-fps', type=float, default=5)
    p.add_argument('--probe-only', action='store_true')
    p.add_argument('--workers', type=int, default=1, choices=range(1,5))
    args = p.parse_args()
    if ((args.limit is not None and args.limit <= 0) or
        (args.max_seconds is not None and (not math.isfinite(args.max_seconds) or args.max_seconds <= 0)) or
        not math.isfinite(args.sample_fps) or not 0 < args.sample_fps <= 30):
        p.error('Limit/duration must be positive and sample FPS must be in (0, 30].')
    source = args.source_root.resolve()
    paths = sorted(x for x in source.rglob('*') if x.is_file() and x.suffix.lower() in MEDIA and not x.name.startswith('._'))
    if args.include_stems:
        wanted = {n.lower() for n in args.include_stems}
        paths = [x for x in paths if x.stem.lower() in wanted]
        missing = wanted - {x.stem.lower() for x in paths}
        if missing: p.error('Missing requested recordings: ' + ', '.join(sorted(missing)))
    if not paths: raise ValueError('No videos found')
    if args.limit: paths = paths[:args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    inventory=[]
    for path in paths:
        relative = str(path.relative_to(source))
        recording_id = 'video_' + hashlib.sha256(relative.encode()).hexdigest()[:12]
        inventory.append({'recording_id':recording_id, 'relative_path':relative, **probe(path)})
    settings={'source_root':str(source), 'sample_fps':args.sample_fps,
              'max_seconds':args.max_seconds,'minimum_event_s':2,
              'selection': {'include_stems':args.include_stems,'limit':args.limit,'order':'sorted relative path'},
              'classifier_hashes':{name:file_hash(Path('data/processed/video_research/phase3')/(name+'.joblib'))
                                    for name in ['head_deviation','eye_deviation']},
              'measurement_model_hashes': {name: file_hash(Path('data/models/video_research') / name)
                    for name in ['face_landmarker.task','mobileone_s0_gaze.onnx']},
              'code_hashes': {name:file_hash(Path(__file__).parent / name)
                    for name in ['batch_transfer.py','video_pipeline.py','features.py']}}
    fingerprint=hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()
    (args.out/'inventory.json').write_text(json.dumps({'settings':settings,'config_sha256':fingerprint,'videos':inventory},indent=2))
    print(f'Inventoried {len(paths)} videos, {sum(x["duration_s"] for x in inventory)/60:.1f} source minutes',flush=True)
    if args.probe_only:return
    summaries=[];errors=[]
    jobs=[(path,item,args.out,fingerprint,args.sample_fps,args.max_seconds) for path,item in zip(paths,inventory)]
    pool=ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn')) if args.workers>1 else None
    try:
        results=(f.result() for f in as_completed([pool.submit(process_one,*job) for job in jobs])) if pool else (process_one(*job) for job in jobs)
        for recording_id,r,error in results:
            if error:
                errors.append({'recording_id':recording_id,'error':error})
                print(f'{recording_id} failed: {error}',flush=True)
            else:
                summaries.append(r)
                print(f'{recording_id}: {r["analyzed_seconds"]:.1f}s, {r["sampled_frames"]} samples, {len(r["events"])} events ({len(summaries)+len(errors)}/{len(jobs)})',flush=True)
            result={**aggregate(summaries),'errors':errors,'expected_recordings':len(jobs),
                    'completed_recordings':len(summaries)+len(errors),'workers':args.workers}
            tmp=args.out/'summary.json.partial'
            tmp.write_text(json.dumps(result,indent=2));tmp.replace(args.out/'summary.json')
    finally:
        if pool:pool.shutdown()
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
