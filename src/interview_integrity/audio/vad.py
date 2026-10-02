"""Simple energy-based voice activity detection (VAD).

This is a transparent baseline used when word-level timestamps are not available.

* By default the threshold adapts to each recording: frames within ``relative_db``
  of the recording's loud (95th percentile) frames count as speech. This handles
  recordings made at very different levels. Pass ``threshold_dbfs`` for a fixed
  threshold instead.
* If the recording has almost no dynamic range (loud frames barely louder than quiet
  ones, e.g. constant hiss with no speech), no speech is reported rather than
  labelling the whole clip as speech.
* It cannot tell the candidate's voice apart from the interviewer's or from other
  sounds; use metadata answer windows (or future diarization) to restrict analysis.
"""

from __future__ import annotations

import math
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

Interval = tuple[float, float]

SILENCE_DBFS = -120.0  # level assigned to digitally silent frames


@dataclass(frozen=True)
class FrameLevels:
    """Per-frame RMS levels (dBFS) of a mono 16-bit WAV, optionally restricted to a window."""

    start: float  # seconds, time of the first frame
    frame_s: float
    db: list[float]
    peak_abs: int  # max absolute sample value in the analyzed audio
    clipped_samples: int  # samples at full scale
    n_samples: int
    sample_rate: int

    @property
    def duration(self) -> float:
        return self.n_samples / self.sample_rate if self.sample_rate else 0.0

    def percentile(self, q: float) -> float | None:
        if not self.db:
            return None
        ranked = sorted(self.db)
        return ranked[int(q * (len(ranked) - 1))]

    def frame_time(self, i: int) -> Interval:
        t0 = self.start + i * self.frame_s
        return (t0, t0 + self.frame_s)


def frame_levels(
    wav_path: str | Path, *, start: float | None = None, end: float | None = None, frame_ms: float = 30.0
) -> FrameLevels:
    """Read a 16-bit PCM WAV (first channel) and compute per-frame dBFS levels."""
    wav_path = Path(wav_path)
    if not wav_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {wav_path}")
    with wave.open(str(wav_path), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError(f"Expected 16-bit PCM WAV, got sample width {wf.getsampwidth()} bytes")
        rate = wf.getframerate()
        n_channels = wf.getnchannels()
        total = wf.getnframes()
        first = min(int((start or 0.0) * rate), total)
        last = total if end is None else min(total, int(end * rate))
        wf.setpos(first)
        raw = wf.readframes(max(0, last - first))

    samples = array("h")
    samples.frombytes(raw)
    if n_channels > 1:
        samples = samples[::n_channels]

    frame_len = max(1, int(rate * frame_ms / 1000))
    db: list[float] = []
    for i in range(0, len(samples) - frame_len + 1, frame_len):
        frame = samples[i : i + frame_len]
        rms = math.sqrt(sum(s * s for s in frame) / frame_len)
        db.append(20 * math.log10(rms / 32768) if rms > 0 else SILENCE_DBFS)
    peak = max((abs(s) for s in samples), default=0)
    clipped = sum(1 for s in samples if s >= 32767 or s <= -32768)
    return FrameLevels(first / rate, frame_len / rate, db, peak, clipped, len(samples), rate)


def _merge(intervals: list[Interval], merge_gap: float) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in intervals:
        if merged and start - merged[-1][1] < merge_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def speech_threshold(
    levels: FrameLevels,
    *,
    threshold_dbfs: float | None = None,
    relative_db: float = 25.0,
    floor_dbfs: float = -75.0,
    min_dynamic_range_db: float = 6.0,
) -> float | None:
    """Speech threshold in dBFS, or ``None`` if no speech can be distinguished."""
    if threshold_dbfs is not None:
        return threshold_dbfs
    p95, p10 = levels.percentile(0.95), levels.percentile(0.10)
    if p95 is None or p10 is None or p95 <= SILENCE_DBFS:
        return None
    if p95 - p10 < min_dynamic_range_db:
        return None  # flat level throughout: constant noise or constant tone, not separable
    return max(p95 - relative_db, floor_dbfs)


def speech_intervals_from_levels(
    levels: FrameLevels, threshold: float | None, *, merge_gap: float = 0.3, min_speech: float = 0.1
) -> list[Interval]:
    if threshold is None:
        return []
    raw = [levels.frame_time(i) for i, d in enumerate(levels.db) if d >= threshold]
    merged = _merge(raw, merge_gap)
    return [(round(s, 3), round(e, 3)) for s, e in merged if e - s >= min_speech]


def detect_speech_intervals(
    wav_path: str | Path,
    *,
    start: float | None = None,
    end: float | None = None,
    frame_ms: float = 30.0,
    threshold_dbfs: float | None = None,
    relative_db: float = 25.0,
    floor_dbfs: float = -75.0,
    min_dynamic_range_db: float = 6.0,
    merge_gap: float = 0.3,
    min_speech: float = 0.1,
) -> list[Interval]:
    """Return ``(start, end)`` second intervals whose frame energy exceeds the speech threshold.

    Threshold: ``threshold_dbfs`` if given, else ``max(p95 - relative_db, floor_dbfs)``
    where ``p95`` is the 95th-percentile frame level (dBFS) of the analyzed audio.
    Gaps shorter than ``merge_gap`` are bridged; intervals shorter than ``min_speech``
    are dropped.
    """
    levels = frame_levels(wav_path, start=start, end=end, frame_ms=frame_ms)
    threshold = speech_threshold(
        levels, threshold_dbfs=threshold_dbfs, relative_db=relative_db,
        floor_dbfs=floor_dbfs, min_dynamic_range_db=min_dynamic_range_db,
    )
    return speech_intervals_from_levels(levels, threshold, merge_gap=merge_gap, min_speech=min_speech)
