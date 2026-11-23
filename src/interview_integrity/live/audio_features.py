"""Lightweight live speech-window feature summary using existing VAD/loudness paths."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ..audio.vad import detect_speech_intervals, frame_levels
from ..features.loudness import extract_loudness_features
from .pcm import write_wav_bytes


def summarize_speech_window(
    pcm: bytes,
    *,
    sample_rate: int,
    session_offset_seconds: float,
) -> dict[str, Any]:
    """Compute unassigned speech-window evidence (not answer-attributed)."""
    if not pcm or sample_rate <= 0:
        return {
            "scope": "session_speech_window",
            "assigned_to_answer": False,
            "speech_seconds": 0.0,
            "note": "empty_audio",
        }

    with tempfile.TemporaryDirectory(prefix="iic-live-feat-") as tmp:
        wav_path = Path(tmp) / "window.wav"
        wav_path.write_bytes(write_wav_bytes(pcm, sample_rate=sample_rate, channels=1))
        try:
            intervals = detect_speech_intervals(wav_path)
            levels = frame_levels(wav_path)
            loudness = extract_loudness_features(levels, intervals)
        except Exception as exc:  # noqa: BLE001 — live path must stay resilient
            return {
                "scope": "session_speech_window",
                "assigned_to_answer": False,
                "speech_seconds": 0.0,
                "window_start_seconds": session_offset_seconds,
                "error": type(exc).__name__,
            }

    speech_seconds = sum(max(0.0, (end - start)) for start, end in intervals)
    pause_gaps: list[float] = []
    for i in range(1, len(intervals)):
        gap = intervals[i][0] - intervals[i - 1][1]
        if gap > 0:
            pause_gaps.append(gap)

    return {
        "scope": "session_speech_window",
        "assigned_to_answer": False,
        "window_start_seconds": round(session_offset_seconds, 3),
        "window_duration_seconds": round(len(pcm) / 2 / float(sample_rate), 3),
        "speech_seconds": round(speech_seconds, 3),
        "speech_interval_count": len(intervals),
        "pause_count": len(pause_gaps),
        "mean_pause_seconds": round(sum(pause_gaps) / len(pause_gaps), 3) if pause_gaps else None,
        "loudness": {
            k: loudness.get(k)
            for k in ("speech_level_mean_dbfs", "speech_level_std_db", "speech_level_range_db")
            if k in loudness
        },
        "note": "Features are session/speech-window evidence only — not mapped to a candidate answer.",
    }
