"""Measured visual features. No identity, emotion, or AI-assistance inference."""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from scipy.spatial.transform import Rotation

HEAD_FEATURES = ['pose_x_deg', 'pose_y_deg', 'pose_z_deg']
EYE_FEATURES = ['iris_a_x', 'iris_a_y', 'iris_b_x', 'iris_b_y',
                'eye_a_open', 'eye_b_open']
ALL_FEATURES = HEAD_FEATURES + EYE_FEATURES
GAZE_FEATURES = ['mobilegaze_yaw_deg', 'mobilegaze_pitch_deg']


class MobileGaze:
    """Published ONNX export; publisher's RGB/ImageNet preprocessing and 90-bin decode.

    https://github.com/yakhyo/gaze-estimation/blob/main/onnx_inference.py
    Face crops here come from MediaPipe, rather than the publisher's RetinaFace.
    """
    def __init__(self, path):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(path), sess_options=opts, providers=['CPUExecutionProvider'])
        self.input = self.session.get_inputs()[0]

    def measure(self, crop):
        size = tuple(self.input.shape[2:][::-1])
        x = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), size).astype(np.float32) / 255
        x = (x - np.array([.485, .456, .406], dtype=np.float32)) / np.array([.229, .224, .225], dtype=np.float32)
        outputs = self.session.run(None, {self.input.name: x.transpose(2, 0, 1)[None]})
        angles = []
        for logits in outputs:
            z = logits[0] - logits[0].max()
            prob = np.exp(z) / np.exp(z).sum()
            angles.append(float(np.sum(prob * np.arange(90)) * 4 - 180))
        return dict(zip(GAZE_FEATURES, angles))


class VisualMeasurements:
    def __init__(self, model_path: Path, video=False, gaze_model=None):
        self.video = video
        self.gaze = MobileGaze(gaze_model) if gaze_model else None
        opts = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model_path),
                                           delegate=python.BaseOptions.Delegate.CPU),
            running_mode=vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE,
            num_faces=2, output_facial_transformation_matrixes=True,
            min_face_detection_confidence=0.5, min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5)
        self.model = vision.FaceLandmarker.create_from_options(opts)

    def close(self):
        self.model.close()

    def measure(self, frame, timestamp_ms=0):
        h, w = frame.shape[:2]
        # CPU budget bound; aspect ratio retained. Coordinates map back to input pixels.
        if w > 960:
            frame = cv2.resize(frame, (960, round(h * 960 / w)))
        image = mp.Image(image_format=mp.ImageFormat.SRGB,
                         data=np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        r = self.model.detect_for_video(image, int(timestamp_ms)) if self.video else self.model.detect(image)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        out = {'face_count': len(r.face_landmarks), 'luma_mean': float(gray.mean()),
               'laplacian_var': float(cv2.Laplacian(gray, cv2.CV_64F).var()),
               'status': 'no_face_detected', **dict.fromkeys(ALL_FEATURES)}
        if len(r.face_landmarks) != 1:
            if len(r.face_landmarks) > 1:
                out['status'] = 'multiple_faces'
            return out
        lm = np.array([(p.x * w, p.y * h, p.z * w) for p in r.face_landmarks[0]])
        angles = Rotation.from_matrix(np.array(r.facial_transformation_matrixes[0])[:3, :3]).as_euler('xyz', degrees=True)
        # Euler values are a camera-relative pose proxy, not calibrated physical angles.
        out.update(dict(zip(HEAD_FEATURES, map(float, angles))))
        out['face_width_px'] = float(np.ptp(lm[:468, 0]))
        out['face_center_x'] = float(lm[:468, 0].mean() / w)
        out['face_center_y'] = float(lm[:468, 1].mean() / h)
        if self.gaze:
            # Predicted face bounds only; annotations never enter preprocessing.
            x1, y1 = np.maximum(lm[:468, :2].min(axis=0), 0).astype(int)
            x2, y2 = np.minimum(lm[:468, :2].max(axis=0), [w, h]).astype(int)
            original = frame
            # lm coordinates refer to the input resolution before budget resizing.
            scale = frame.shape[1] / w
            crop = original[round(y1 * scale):round(y2 * scale), round(x1 * scale):round(x2 * scale)]
            if crop.size:
                out.update(self.gaze.measure(crop))
        eye_quality = []
        for key, corner1, corner2, top, bottom, iris in [
            ('a', 33, 133, 159, 145, 468), ('b', 362, 263, 386, 374, 473)]:
            a, b, p = lm[corner1, :2], lm[corner2, :2], lm[iris, :2]
            axis = b - a
            width = np.linalg.norm(axis)
            normal = np.array([-axis[1], axis[0]]) / max(width, 1e-9)
            openness = np.linalg.norm(lm[top, :2] - lm[bottom, :2]) / max(width, 1e-9)
            out[f'iris_{key}_x'] = float(np.dot(p - a, axis) / max(width ** 2, 1e-9))
            out[f'iris_{key}_y'] = float(np.dot(p - (a + b) / 2, normal) / max(width, 1e-9))
            out[f'eye_{key}_open'] = float(openness)
            eye_quality.append(width >= 12 and openness >= 0.10)
        out['status'] = 'ok' if all(eye_quality) and out['face_width_px'] >= 80 else 'eye_quality_low'
        return out


def annotation(path: Path):
    rows = [list(map(float, line.split())) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        return {'head_label': None, 'eye_label': None}
    if any(len(r) != 5 or not all(math.isfinite(v) for v in r) for r in rows):
        raise ValueError('Invalid YOLO annotation: ' + str(path))
    heads = [r for r in rows if int(r[0]) in range(5)]
    eyes = [int(r[0]) for r in rows if int(r[0]) in range(5, 10)]
    return {'head_label': int(max(heads, key=lambda r: r[3] * r[4])[0]) if heads else None,
            'eye_label': eyes[0] if len(eyes) == 2 and len(set(eyes)) == 1 else None}


def events_from_rows(rows, sample_fps, min_duration=2.0):
    """Merge consecutive measured events; missing/low-quality eyes never become gaze evidence."""
    names = ('no_face_detected', 'multiple_faces', 'head_deviation', 'eye_deviation')
    events = []
    for name in names:
        start = last = None
        def finish():
            if start is not None and last + 1 / sample_fps - start >= min_duration - 1e-8:
                events.append({'type': name, 'start_s': round(start, 3),
                               'end_s': round(last + 1 / sample_fps, 3),
                               'duration_s': round(last + 1 / sample_fps - start, 3)})
        for r in rows:
            active = (r['status'] == name if name in names[:2] else r.get(name) is True)
            t = r['timestamp_s']
            if active:
                if last is not None and t - last > 1.5 / sample_fps:
                    finish()
                    start = None
                if start is None:
                    start = t
                last = t
            else:
                finish()
                start = last = None
        finish()
    return sorted(events, key=lambda e: (e['start_s'], e['type']))
