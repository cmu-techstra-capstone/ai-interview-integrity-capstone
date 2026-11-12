"""Deterministic follow-up pattern: delayed start + look-away + fluent answer.

This is a hand-written review rule, not a trained or validated detector. It has no
AI-assistance ground truth behind it. Its output says *which measured conditions were
met* for one answer, so a human can decide whether to ask a follow-up question. It never
produces a probability and never says a candidate used AI.

Required conditions (all three must be met to suggest a follow-up):

1. ``delayed_start``: the answer starts at least ``min_latency_s`` after the question ends.
2. ``look_away``: a sustained baseline-relative head or gaze change (from the video
   research timeline) overlaps the period from question end to a few seconds into the
   answer.
3. ``fluent_answer``: the answer has no more fillers and long pauses than this candidate's
   own median answer (a within-person comparison, so habitual speaking style is not
   penalised).

Optional context (reported, never required): ``read_like_delivery`` from the audio
read-vs-spontaneous model and ``ai_like_text`` from the transcript detector. Both were
trained on non-interview data; their scores are shown as context only.

Any required condition that cannot be measured makes the result ``insufficient_evidence``
rather than a guess.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .turns import FILLERS, AnswerWindow, tokenize

MET, NOT_MET, UNMEASURABLE = "met", "not_met", "unmeasurable"
SUGGEST, NO_PATTERN, INSUFFICIENT = "suggest_followup", "no_pattern", "insufficient_evidence"
REQUIRED = ("delayed_start", "look_away", "fluent_answer")


@dataclass(frozen=True)
class FollowupConfig:
    min_latency_s: float = 2.0
    look_window_into_answer_s: float = 3.0
    min_visual_coverage: float = 0.5  # measured frames / expected frames in the look window
    sample_fps: float = 2.0
    long_pause_s: float = 1.0
    min_answer_words: int = 15
    min_answers_for_self_baseline: int = 3
    read_like_threshold: float = 0.5
    ai_like_text_threshold: float = 0.5


@dataclass(frozen=True)
class VisualTrack:
    """Per-recording output of ``experiments/video/relative_events.py``."""
    measurements: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]
    calibration_seconds: float
    head_baseline_available: bool
    gaze_baseline_available: bool

    @classmethod
    def from_timeline(cls, timeline: Mapping[str, Any], measurements: Iterable[Mapping[str, Any]]) -> "VisualTrack":
        return cls(
            measurements=tuple(dict(m) for m in measurements),
            events=tuple(dict(e) for e in timeline.get("events", [])),
            calibration_seconds=float(timeline.get("calibration_seconds", 30)),
            head_baseline_available=bool(timeline.get("head_baseline_available")),
            gaze_baseline_available=bool(timeline.get("gaze_baseline_available")),
        )


@dataclass(frozen=True)
class ConditionResult:
    name: str
    status: str
    value: float | int | None
    threshold: str
    explanation: str
    modality: str
    timestamps: tuple[tuple[float, float], ...] = ()
    required: bool = True


@dataclass(frozen=True)
class FollowupResult:
    recording_id: str
    question_id: str
    status: str
    conditions: tuple[ConditionResult, ...]
    question_end: float | None
    answer_start: float | None
    answer_end: float | None
    question_text: str = ""
    ai_assistance_probability: None = None  # deliberately always None
    notes: tuple[str, ...] = field(default=())

    def condition(self, name: str) -> ConditionResult:
        return next(c for c in self.conditions if c.name == name)

    def to_dict(self, include_text: bool = False) -> dict[str, Any]:
        d = asdict(self)
        if not include_text:
            d.pop("question_text", None)
        return d

    def evidence_signals(self) -> list[dict[str, Any]]:
        """Conditions in the shape of ``docs/evidence-contract.md`` (confidence stays None)."""
        out = []
        for c in self.conditions:
            out.append({
                "signal_name": f"fusion_{c.name}",
                "modality": c.modality,
                "value": c.value,
                "confidence": None,
                "quality_status": "unknown" if c.status == UNMEASURABLE else "ok",
                "supporting_timestamps": [list(t) for t in c.timestamps],
                "supporting_transcript_span": None,
                "explanation": c.explanation,
                "source_features": [f"fusion_{c.name}"],
                "sample_key": f"{self.recording_id}/{self.question_id}",
            })
        return out


# ---------------------------------------------------------------- fluency measures

def filler_rate(text: str) -> float | None:
    """Fillers per 100 words, from the human transcript (ASR often drops fillers)."""
    toks = tokenize(text)
    if not toks:
        return None
    return 100.0 * sum(t in FILLERS for t in toks) / len(toks)


def long_pause_rate(window: AnswerWindow, long_pause_s: float) -> float | None:
    """Gaps >= ``long_pause_s`` between consecutive ASR words, per minute of answer."""
    w = window.answer_words
    if len(w) < 2:
        return None
    span = w[-1].end - w[0].start
    if span <= 0:
        return None
    gaps = sum(1 for a, b in zip(w, w[1:]) if b.start - a.end >= long_pause_s)
    return 60.0 * gaps / span


def _fluency(window: AnswerWindow, cfg: FollowupConfig) -> tuple[float | None, float | None]:
    if len(tokenize(window.answer_text)) < cfg.min_answer_words or not window.timing_ok:
        return None, None
    return filler_rate(window.answer_text), long_pause_rate(window, cfg.long_pause_s)


# ---------------------------------------------------------------- conditions

def _delayed_start(window: AnswerWindow, cfg: FollowupConfig) -> ConditionResult:
    thr = f">= {cfg.min_latency_s:g} s"
    if not window.timing_ok or window.latency is None:
        return ConditionResult("delayed_start", UNMEASURABLE, None, thr,
                               f"Response latency not measurable ({window.timing_note or 'no timing'}).", "audio")
    lat = round(window.latency, 2)
    span = ((round(window.question_end, 2), round(max(window.answer_start, window.question_end), 2)),)
    status = MET if lat >= cfg.min_latency_s else NOT_MET
    return ConditionResult("delayed_start", status, lat, thr,
                           f"Answer started {lat:.2f} s after the question ended.", "audio", span)


def _look_away(window: AnswerWindow, track: VisualTrack | None, cfg: FollowupConfig) -> ConditionResult:
    thr = "sustained (>= 2 s) head or gaze change >= 15 deg from own baseline"
    if track is None:
        return ConditionResult("look_away", UNMEASURABLE, None, thr, "No visual timeline for this recording.", "visual")
    if not window.timing_ok or window.question_end is None or window.answer_start is None:
        return ConditionResult("look_away", UNMEASURABLE, None, thr, "Look window not defined (answer timing not measurable).", "visual")
    a = window.question_end
    b = max(window.answer_start, window.question_end) + cfg.look_window_into_answer_s
    if a < track.calibration_seconds:
        return ConditionResult("look_away", UNMEASURABLE, None, thr,
                               f"Look window starts inside the {track.calibration_seconds:g} s baseline period.", "visual")
    if not (track.head_baseline_available or track.gaze_baseline_available):
        return ConditionResult("look_away", UNMEASURABLE, None, thr, "No head or gaze baseline for this recording.", "visual")
    frames = [m for m in track.measurements if a <= m.get("timestamp_s", -1) <= b]
    measured = [m for m in frames if m.get("head_deviation") is not None or m.get("eye_deviation") is not None]
    expected = max(1.0, (b - a) * cfg.sample_fps)
    coverage = len(measured) / expected
    if coverage < cfg.min_visual_coverage:
        return ConditionResult("look_away", UNMEASURABLE, None, thr,
                               f"Only {coverage:.0%} of the look window has head/gaze measurements.", "visual")
    hits = [e for e in track.events
            if e.get("type") in ("relative_head_change", "relative_gaze_change")
            and e["start_s"] < b and e["end_s"] > a]
    if not hits:
        return ConditionResult("look_away", NOT_MET, 0.0, thr,
                               f"No sustained head/gaze change between {a:.1f} s and {b:.1f} s.", "visual")
    overlap = sum(min(e["end_s"], b) - max(e["start_s"], a) for e in hits)
    kinds = sorted({e["type"].replace("relative_", "").replace("_change", "") for e in hits})
    spans = tuple((round(e["start_s"], 2), round(e["end_s"], 2)) for e in hits)
    return ConditionResult("look_away", MET, round(overlap, 2), thr,
                           f"Sustained {'/'.join(kinds)} change from own baseline overlapping "
                           f"{a:.1f}-{b:.1f} s for {overlap:.1f} s.", "visual", spans)


def _fluent(window: AnswerWindow, baseline: tuple[float, float] | None, cfg: FollowupConfig) -> ConditionResult:
    thr = "filler rate and long-pause rate both <= candidate's own median answer"
    fr, pr = _fluency(window, cfg)
    if fr is None or pr is None:
        return ConditionResult("fluent_answer", UNMEASURABLE, None, thr,
                               "Fluency not measurable (answer too short or timing unreliable).", "audio")
    if baseline is None:
        return ConditionResult("fluent_answer", UNMEASURABLE, None, thr,
                               f"Fewer than {cfg.min_answers_for_self_baseline} measurable answers for a personal baseline.", "audio")
    mf, mp = baseline
    met = fr <= mf and pr <= mp
    span = ((round(window.answer_start, 2), round(window.answer_end, 2)),) if window.answer_end is not None else ()
    return ConditionResult("fluent_answer", MET if met else NOT_MET, round(fr, 2), thr,
                           f"Fillers {fr:.1f}/100 words (own median {mf:.1f}); long pauses "
                           f"{pr:.1f}/min (own median {mp:.1f}).", "audio", span)


def _optional_score(name: str, score: float | None, threshold: float, modality: str, label: str) -> ConditionResult:
    thr = f">= {threshold:g} (context only; model not trained on interviews)"
    if score is None:
        return ConditionResult(name, UNMEASURABLE, None, thr, f"{label} score not provided.", modality, required=False)
    return ConditionResult(name, MET if score >= threshold else NOT_MET, round(float(score), 3), thr,
                           f"{label} score {score:.2f}.", modality, required=False)


def self_baseline(windows: list[AnswerWindow], cfg: FollowupConfig) -> tuple[float, float] | None:
    vals = [v for v in (_fluency(w, cfg) for w in windows) if v[0] is not None and v[1] is not None]
    if len(vals) < cfg.min_answers_for_self_baseline:
        return None
    return statistics.median(v[0] for v in vals), statistics.median(v[1] for v in vals)


def combine(conditions: tuple[ConditionResult, ...]) -> str:
    req = [c for c in conditions if c.required]
    if any(c.status == NOT_MET for c in req):
        return NO_PATTERN
    if any(c.status == UNMEASURABLE for c in req):
        return INSUFFICIENT
    return SUGGEST


def evaluate_window(recording_id: str, window: AnswerWindow, track: VisualTrack | None,
                    baseline: tuple[float, float] | None, cfg: FollowupConfig = FollowupConfig(),
                    read_like_score: float | None = None, ai_text_score: float | None = None) -> FollowupResult:
    conds = (
        _delayed_start(window, cfg),
        _look_away(window, track, cfg),
        _fluent(window, baseline, cfg),
        _optional_score("read_like_delivery", read_like_score, cfg.read_like_threshold, "audio", "Read-like delivery (audio model)"),
        _optional_score("ai_like_text", ai_text_score, cfg.ai_like_text_threshold, "transcript", "AI-like text (transcript model)"),
    )
    return FollowupResult(
        recording_id=recording_id, question_id=window.question_id, status=combine(conds),
        conditions=conds, question_end=window.question_end, answer_start=window.answer_start,
        answer_end=window.answer_end, question_text=window.question_text,
        notes=(window.timing_note,) if window.timing_note else (),
    )


def evaluate_interview(recording_id: str, windows: list[AnswerWindow], track: VisualTrack | None,
                       cfg: FollowupConfig = FollowupConfig(),
                       read_like_scores: Mapping[str, float] | None = None,
                       ai_text_scores: Mapping[str, float] | None = None) -> list[FollowupResult]:
    baseline = self_baseline(windows, cfg)
    rl, at = read_like_scores or {}, ai_text_scores or {}
    return [evaluate_window(recording_id, w, track, baseline, cfg, rl.get(w.question_id), at.get(w.question_id))
            for w in windows]
