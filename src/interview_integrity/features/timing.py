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
LONG_PAUSE = 1.0  # seconds; long enough to read, look something up or re-plan
MIN_WORDS_PER_SEGMENT = 3  # segments with fewer words are too short for a stable rate


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


def _std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def speech_rate_cv(words: Sequence[Word], intervals: Sequence[Interval]) -> float | None:
    """Coefficient of variation of words-per-second across speech segments.

    Requires word timestamps. Low values mean a very even pace (as in reading aloud);
    ``None`` when fewer than two segments have enough words.
    """
    timed = [w for w in words if w.has_timestamps]
    rates = []
    for s, e in intervals:
        n = sum(1 for w in timed if s <= (w.start + w.end) / 2 <= e)  # type: ignore[operator]
        if n >= MIN_WORDS_PER_SEGMENT and e > s:
            rates.append(n / (e - s))
    sd = _std(rates)
    return sd / (sum(rates) / len(rates)) if sd is not None else None


def compute_timing_features(
    *,
    speech_intervals: Sequence[Interval] | None,
    answer_start: float | None,
    answer_end: float | None,
    question_end: float | None = None,
    word_count: int | None = None,
    words: Sequence[Word] | None = None,
    min_pause: float = DEFAULT_MIN_PAUSE,
) -> dict[str, Any]:
    """Compute answer duration, speech/silence duration, pauses, speech segments, rates, latency.

    ``words`` (with timestamps) enables ``speech_rate_cv``; otherwise it is ``None``.
    """
    duration = answer_end - answer_start if answer_start is not None and answer_end is not None else None
    latency = answer_start - question_end if answer_start is not None and question_end is not None else None

    features: dict[str, Any] = {
        "speech_duration": None,
        "silence_duration": None,
        "pause_count": None,
        "long_pause_count": None,
        "mean_pause_duration": None,
        "max_pause_duration": None,
        "pause_duration_std": None,
        "total_pause_duration": None,
        "pause_ratio": None,
        "speech_segment_count": None,
        "mean_speech_segment_duration": None,
        "speech_segment_duration_std": None,
        "speech_rate_wpm": None,
        "articulation_rate_wpm": None,
        "speech_rate_cv": None,
    }

    if duration and word_count:
        features["speech_rate_wpm"] = _r(60 * word_count / duration)

    if speech_intervals is None or duration is None:
        return {"answer_duration": _r(duration), "response_latency": _r(latency), **features}

    intervals = _clip(sorted(speech_intervals), answer_start, answer_end)  # type: ignore[arg-type]
    speech = sum(e - s for s, e in intervals)
    pauses = [b[0] - a[1] for a, b in zip(intervals, intervals[1:]) if b[0] - a[1] >= min_pause]

    segments = [e - s for s, e in intervals]
    features.update(
        speech_duration=_r(speech),
        silence_duration=_r(max(duration - speech, 0.0)),
        pause_count=len(pauses),
        long_pause_count=sum(1 for p in pauses if p >= LONG_PAUSE),
        mean_pause_duration=_r(sum(pauses) / len(pauses)) if pauses else None,
        max_pause_duration=_r(max(pauses)) if pauses else None,
        pause_duration_std=_r(_std(pauses)),
        total_pause_duration=_r(sum(pauses)),
        pause_ratio=_r(sum(pauses) / duration) if duration else None,
        speech_segment_count=len(segments),
        mean_speech_segment_duration=_r(speech / len(segments)) if segments else None,
        speech_segment_duration_std=_r(_std(segments)),
        articulation_rate_wpm=_r(60 * word_count / speech) if word_count and speech else None,
        speech_rate_cv=_r(speech_rate_cv(words, intervals)) if words else None,
    )
    return {"answer_duration": _r(duration), "response_latency": _r(latency), **features}
