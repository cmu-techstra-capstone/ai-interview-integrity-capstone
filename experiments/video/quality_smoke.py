"""Generated all-black clip tests detection loss/timestamps, not real absence accuracy."""
from pathlib import Path
import cv2
import numpy as np
from video_pipeline import run

if __name__ == '__main__':
    root=Path('data/processed/video_research')
    path=root/'black_3s.mp4'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),20,(320,240))
    if not writer.isOpened():raise ValueError('Cannot create test video')
    for _ in range(60):writer.write(np.zeros((240,320,3),dtype=np.uint8))
    writer.release()
    result=run(path,Path('data/models/video_research/face_landmarker.task'),root/'phase2',root/'demo_black',gaze_model=Path('data/models/video_research/mobileone_s0_gaze.onnx'))
    assert result['quality_status']=={'no_face_detected':15}
    assert result['events']==[{'type':'no_face_detected','start_s':0.0,'end_s':3.0,'duration_s':3.0}]
    assert result['ai_assistance_probability'] is None
    print('Full-video no-face timing smoke passed: 15 samples, one exact 0–3 s event, no AI probability.')
