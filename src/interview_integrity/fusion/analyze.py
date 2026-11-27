"""One recording -> one dashboard JSON (post-interview analysis).

Pure orchestration: the caller supplies turns, the visual track and, when needed, ASR words.
Heavy steps (MediaPipe, gaze model, faster-whisper) live in ``experiments/fusion/analyze_video.py``.
The output never contains a probability or a verdict.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Mapping

from ..llm.base import LLMClient
from .demo_export import SCHEMA, answer_fragment, recording_payload
from .followup import SUGGEST, FollowupConfig, VisualTrack, evaluate_interview
from .llm_brief import generate_brief
from .turns import TimedTurn, Turn, Word, align_turns, build_answer_windows


def answer_windows(turns: list[Turn] | list[TimedTurn], asr_words: list[Word] | None):
    """Timed transcript with words -> use as is; otherwise align ASR words to the turns."""
    if asr_words:
        plain = [Turn(t.speaker, t.text) for t in turns]
        return build_answer_windows(align_turns(plain, asr_words)), "asr_alignment"
    if turns and isinstance(turns[0], TimedTurn):
        return build_answer_windows(list(turns)), "transcript_timestamps"
    raise ValueError("untimed transcript needs ASR word timestamps")


def visual_summary(track: VisualTrack | None, timeline: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if track is None:
        return {"available": False, "events": []}
    tl = timeline or {}
    return {
        "available": True,
        "calibration_seconds": track.calibration_seconds,
        "head_baseline_available": track.head_baseline_available,
        "gaze_baseline_available": track.gaze_baseline_available,
        "angle_change_threshold_degrees": tl.get("angle_change_threshold_degrees"),
        "minimum_event_seconds": tl.get("minimum_event_seconds"),
        "signal_coverage": tl.get("signal_coverage"),
        "events": [{"type": e.get("type"), "start_s": e.get("start_s"), "end_s": e.get("end_s"),
                    "duration_s": e.get("duration_s")} for e in track.events],
        "note": "Look-away events are changes from this candidate's own baseline, not evidence of AI use.",
    }


def analyze_recording(recording_id: str, turns: list[Turn] | list[TimedTurn], track: VisualTrack | None, *,
                      asr_words: list[Word] | None = None, cfg: FollowupConfig = FollowupConfig(),
                      timeline: Mapping[str, Any] | None = None, brief_client: LLMClient | None = None,
                      brief_model: str | None = None, include_text: bool = False,
                      source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    windows, timing_source = answer_windows(turns, asr_words)
    results = evaluate_interview(recording_id, windows, track, cfg)
    fragments, n_briefs, n_accepted = [], 0, 0
    for r in results:
        brief = None
        if brief_client is not None and r.status == SUGGEST:
            brief = generate_brief(brief_client, r, model=brief_model or "openai/gpt-4o-mini")
            n_briefs += 1
            n_accepted += bool(brief["accepted"])
        fragments.append(answer_fragment(r, brief, include_text=include_text))
    payload = recording_payload(recording_id, fragments)
    payload.update({
        "schema": SCHEMA,
        "analysis_type": "post_interview",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": dict(source or {}),
        "timing_source": timing_source,
        "answer_windows": len(windows),
        "windows_with_reliable_timing": sum(w.timing_ok for w in windows),
        "settings": asdict(cfg),
        "visual": visual_summary(track, timeline),
        "reviewer_briefs": {"requested": n_briefs, "accepted": n_accepted,
                            "model": brief_model if brief_client is not None else None},
        "ai_assistance_probability": None,
    })
    return payload
