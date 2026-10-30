"""Re-extract Columbia gaze using a challenger with the same MediaPipe crop code."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import cv2
import numpy as np

from features import VisualMeasurements
from video_pipeline import file_hash


def extract(model_path, output):
    raw=Path('data/raw/video_research/columbia')
    manifest=json.loads((raw/'manifest.json').read_text())
    landmarker=Path('data/models/video_research/face_landmarker.task')
    model=VisualMeasurements(landmarker,gaze_model=model_path)
    output.parent.mkdir(parents=True,exist_ok=True)
    times=[];quality=Counter()
    try:
        with output.open('w') as out:
            for i,item in enumerate(manifest['records']):
                source=raw/item['file']
                if file_hash(source)!=item['sha256']:raise ValueError('Source image changed')
                image=cv2.imread(str(source))
                if image is None:raise ValueError('Failed to decode image')
                start=time.perf_counter();row=model.measure(image);times.append(1000*(time.perf_counter()-start))
                quality.update([row['status']]);row.update(item)
                row['label']=int(abs(item['gaze_horizontal_deg'])>=10 or abs(item['gaze_vertical_deg'])>=10)
                row['measurement_ms']=times[-1]
                out.write(json.dumps(row,allow_nan=False)+'\n')
                if (i+1)%100==0:print(f'Measured {i+1}/{len(manifest["records"])}',flush=True)
    finally:model.close()
    provenance={'model_filename':model_path.name,'model_sha256':file_hash(model_path),
        'model_bytes':model_path.stat().st_size,'landmarker_sha256':file_hash(landmarker),
        'feature_code_sha256':file_hash(Path(__file__).parent/'features.py'),
        'features_sha256':file_hash(output),'frames':len(times),'quality_counts':dict(quality),
        'median_full_measurement_ms':float(np.median(times)),'p95_full_measurement_ms':float(np.percentile(times,95)),
        'timing_scope':'Includes detection, image resize, crop and gaze; concurrent MIT workers, not an isolated speed benchmark.',
        'source':'https://github.com/yakhyo/gaze-estimation/releases/download/weights/resnet34_gaze.onnx',
        'crop':'Same MediaPipe crop and publisher RGB/ImageNet/90-bin preprocessing as MobileOne-S0.'}
    output.with_suffix('.provenance.json').write_text(json.dumps(provenance,indent=2))
    print(json.dumps(provenance,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,default=Path('data/models/video_research/resnet34_gaze.onnx'))
    p.add_argument('--out',type=Path,default=Path('data/processed/video_research/columbia_resnet34.jsonl'))
    args=p.parse_args();extract(args.model,args.out)
