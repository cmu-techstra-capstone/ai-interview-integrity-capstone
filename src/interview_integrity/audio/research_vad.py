"""Optional Silero ONNX comparison adapter, never used by the default pipeline."""
from __future__ import annotations

import math
import wave
from pathlib import Path

SILERO_SETTINGS = {"threshold": 0.5, "min_speech_duration_ms": 100,
                   "min_silence_duration_ms": 300, "speech_pad_ms": 0}


def read_window(path: Path, start: float, end: float):
    """Read a complete normalized window, rejecting truncation rather than padding."""
    import numpy as np
    if not all(math.isfinite(t) for t in (start, end)) or start < 0 or end <= start:
        raise ValueError("Invalid audio window")
    with wave.open(str(path), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, 16000):
            raise ValueError("Research audio must be 16 kHz mono 16-bit PCM")
        first, last = round(start * 16000), round(end * 16000)
        if last > stream.getnframes():
            raise ValueError("Truncated research window")
        stream.setpos(first)
        pcm = stream.readframes(last - first)
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0, pcm


def sample_intervals(timestamps, *, samples: int, start: float = 0.0):
    intervals, previous = [], 0
    for span in timestamps:
        lo, hi = span["start"], span["end"]
        if not 0 <= lo < hi <= samples or lo < previous:
            raise ValueError("Invalid or overlapping Silero timestamps")
        intervals.append((start + lo / 16000, start + hi / 16000))
        previous = hi
    return intervals


class SileroDetector:
    def __init__(self):
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad
        torch.set_num_threads(1)
        self.model = load_silero_vad(onnx=True)
        self.timestamps = get_speech_timestamps

    def detect(self, samples, *, start=0.0):
        import torch
        # Library resets recurrent state on each call; no state crosses windows.
        spans = self.timestamps(torch.from_numpy(samples), self.model, sampling_rate=16000,
                                return_seconds=False, **SILERO_SETTINGS)
        return sample_intervals(spans, samples=len(samples), start=start)


def disagreement_seconds(left, right):
    """Symmetric difference of nonoverlapping intervals, not an accuracy metric."""
    intersection = sum(max(0.0, min(a1, b1) - max(a0, b0))
                       for a0, a1 in left for b0, b1 in right)
    duration = sum(hi - lo for lo, hi in (*left, *right))
    return max(0.0, duration - 2 * intersection)
