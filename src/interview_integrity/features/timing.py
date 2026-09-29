"""Explainable timing features computed from speech intervals.

Speech intervals come from word timestamps (preferred) or energy-based VAD.
All times are seconds. Values that cannot be measured are ``None``; in particular
``response_latency`` is ``None`` unless the question end time is known.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..transcription.base import Word

Interval = tuple[float, float]

DEFAULT_MIN_PAUSE = 0.3  # seconds of silence counted as a pause


def speech_intervals_from_words(words: Sequence[Word], merge_gap: float = DEFAULT_MIN_PAUSE) -> list[Interval]:
    """Merge timestamped words into continuous speech intervals.

    Words separated by less than ``merge_gap`` belong to the same interval.
    """
    spans = sorted((w.start, w.end) for w in words if w.has_timestamps)
    intervals: list[Interval] = []
    for start, end in spans:  # type: ignore[misc]
        if intervals and start - intervals[-1][1] < merge_gap:
            intervals[-1] = (intervals[-1][0], max(intervals[-1][1], end))
        else:
            intervals.append((start, end))
    return intervals


def _clip(intervals: Sequence[Interval], lo: float, hi: float) -> list[Interval]:
    out = []
    for s, e in intervals:
        s, e = max(s, lo), min(e, hi)
        if e > s:
            out.append((s, e))
    return out


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def compute_timing_features(
    *,
    speech_intervals: Sequence[Interval] | None,
    answer_start: float | None,
    answer_end: float | None,
    question_end: float | None = None,
    word_count: int | None = None,
    min_pause: float = DEFAULT_MIN_PAUSE,
) -> dict[str, Any]:
    """Compute answer duration, speech duration, pauses, speech rate and latency."""
    duration = answer_end - answer_start if answer_start is not None and answer_end is not None else None
    latency = answer_start - question_end if answer_start is not None and question_end is not None else None

    features: dict[str, Any] = {
        "speech_duration": None,
        "pause_count": None,
        "mean_pause_duration": None,
        "max_pause_duration": None,
        "total_pause_duration": None,
        "pause_ratio": None,
        "speech_rate_wpm": None,
        "articulation_rate_wpm": None,
    }

    if duration and word_count:
        features["speech_rate_wpm"] = _r(60 * word_count / duration)

    if speech_intervals is None or duration is None:
        return {"answer_duration": _r(duration), "response_latency": _r(latency), **features}

    intervals = _clip(sorted(speech_intervals), answer_start, answer_end)  # type: ignore[arg-type]
    speech = sum(e - s for s, e in intervals)
    pauses = [b[0] - a[1] for a, b in zip(intervals, intervals[1:]) if b[0] - a[1] >= min_pause]

    features.update(
        speech_duration=_r(speech),
        pause_count=len(pauses),
        mean_pause_duration=_r(sum(pauses) / len(pauses)) if pauses else None,
        max_pause_duration=_r(max(pauses)) if pauses else None,
        total_pause_duration=_r(sum(pauses)),
        pause_ratio=_r(sum(pauses) / duration) if duration else None,
        articulation_rate_wpm=_r(60 * word_count / speech) if word_count and speech else None,
    )
    return {"answer_duration": _r(duration), "response_latency": _r(latency), **features}
