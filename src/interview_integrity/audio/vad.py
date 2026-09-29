"""Simple energy-based voice activity detection (VAD).

This is a transparent baseline used only when word-level timestamps are not
available. Known limitations:

* A fixed dBFS threshold is sensitive to microphone gain and background noise.
* It cannot tell the candidate's voice apart from the interviewer's or from
  other sounds; use metadata answer windows (or future diarization) to restrict
  analysis to the candidate's answer.
"""

from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path

Interval = tuple[float, float]


def _merge(intervals: list[Interval], merge_gap: float) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in intervals:
        if merged and start - merged[-1][1] < merge_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def detect_speech_intervals(
    wav_path: str | Path,
    *,
    start: float | None = None,
    end: float | None = None,
    frame_ms: float = 30.0,
    threshold_dbfs: float = -40.0,
    merge_gap: float = 0.3,
    min_speech: float = 0.1,
) -> list[Interval]:
    """Return ``(start, end)`` second intervals whose frame energy exceeds ``threshold_dbfs``.

    Only 16-bit PCM WAV is supported (the format produced by ``extract_audio``).
    Gaps shorter than ``merge_gap`` are bridged; intervals shorter than
    ``min_speech`` are dropped.
    """
    wav_path = Path(wav_path)
    if not wav_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {wav_path}")

    with wave.open(str(wav_path), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError(f"Expected 16-bit PCM WAV, got sample width {wf.getsampwidth()} bytes")
        rate = wf.getframerate()
        n_channels = wf.getnchannels()
        first = int((start or 0.0) * rate)
        last = wf.getnframes() if end is None else min(wf.getnframes(), int(end * rate))
        wf.setpos(min(first, wf.getnframes()))
        raw = wf.readframes(max(0, last - first))

    samples = array("h")
    samples.frombytes(raw)
    if n_channels > 1:
        samples = samples[::n_channels]  # first channel only

    frame_len = max(1, int(rate * frame_ms / 1000))
    offset = first / rate
    raw_intervals: list[Interval] = []
    for i in range(0, len(samples), frame_len):
        frame = samples[i : i + frame_len]
        if not frame:
            break
        rms = math.sqrt(sum(s * s for s in frame) / len(frame))
        dbfs = 20 * math.log10(rms / 32768) if rms > 0 else -math.inf
        if dbfs >= threshold_dbfs:
            t0 = offset + i / rate
            raw_intervals.append((t0, t0 + len(frame) / rate))

    merged = _merge(raw_intervals, merge_gap)
    return [(round(s, 3), round(e, 3)) for s, e in merged if e - s >= min_speech]
