"""Loudness of the answer's speech frames (energy only; no pitch or spectral models).

Computed from the same per-frame RMS levels the VAD uses. Values are relative to the
recording (dB differences), except ``speech_level_mean_dbfs`` which depends on
microphone gain and should not be compared across recording setups without care.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..audio.vad import FrameLevels

Interval = tuple[float, float]


def _pct(values: list[float], q: float) -> float:
    ranked = sorted(values)
    return ranked[int(q * (len(ranked) - 1))]


def extract_loudness_features(levels: FrameLevels | None, speech_intervals: Sequence[Interval]) -> dict[str, Any]:
    keys = ("speech_level_mean_dbfs", "speech_level_std_db", "speech_level_range_db")
    if levels is None or not speech_intervals:
        return dict.fromkeys(keys)
    frames = []
    for i, db in enumerate(levels.db):
        t0, t1 = levels.frame_time(i)
        mid = (t0 + t1) / 2
        if any(s <= mid <= e for s, e in speech_intervals):
            frames.append(db)
    if len(frames) < 2:
        return dict.fromkeys(keys)
    mean = sum(frames) / len(frames)
    std = (sum((d - mean) ** 2 for d in frames) / (len(frames) - 1)) ** 0.5
    return {
        "speech_level_mean_dbfs": round(mean, 2),
        "speech_level_std_db": round(std, 2),  # loudness variation; low = monotone delivery
        "speech_level_range_db": round(_pct(frames, 0.9) - _pct(frames, 0.1), 2),
    }
