"""Export follow-up results (and optional LLM reviewer briefs) for a demo UI.

The per-answer fragment uses the same ``evidence_signals`` shape as ``analysis.v1``
(PR #10), plus a ``followup_pattern`` block. It never contains a probability or verdict.
Raw interview text is excluded unless ``include_text=True``.
"""

from __future__ import annotations

from typing import Any, Mapping

from .followup import ConditionResult, FollowupResult

SCHEMA = "followup_pattern.v1"
DISCLAIMER = ("Unvalidated review rule. It suggests where a follow-up question may help; "
              "it does not indicate that the candidate used AI.")


def result_from_dict(d: Mapping[str, Any]) -> FollowupResult:
    """Rebuild a ``FollowupResult`` from ``FollowupResult.to_dict()`` output."""
    conds = tuple(ConditionResult(**{**c, "timestamps": tuple(tuple(t) for t in c.get("timestamps", ()))})
                  for c in d["conditions"])
    return FollowupResult(
        recording_id=d["recording_id"], question_id=d["question_id"], status=d["status"], conditions=conds,
        question_end=d.get("question_end"), answer_start=d.get("answer_start"), answer_end=d.get("answer_end"),
        question_text=d.get("question_text", ""), notes=tuple(d.get("notes", ())),
    )


def answer_fragment(result: FollowupResult, brief: Mapping[str, Any] | None = None,
                    include_text: bool = False) -> dict[str, Any]:
    """One answer for the demo. ``brief`` is the dict returned by ``llm_brief.generate_brief``."""
    if brief is None:
        brief_status, brief_body = "not_requested", None
    elif brief.get("accepted"):
        brief_status, brief_body = "accepted", brief.get("brief")
    else:  # rejected briefs are never shown
        brief_status, brief_body = "rejected", None
    out = {
        "recording_id": result.recording_id,
        "question_id": result.question_id,
        "question_end": result.question_end,
        "answer_start": result.answer_start,
        "answer_end": result.answer_end,
        "evidence_signals": result.evidence_signals(),
        "followup_pattern": {
            "schema": SCHEMA,
            "status": result.status,
            "ai_assistance_probability": None,
            "disclaimer": DISCLAIMER,
            "conditions": [
                {"name": c.name, "required": c.required, "status": c.status, "value": c.value,
                 "threshold": c.threshold, "explanation": c.explanation,
                 "timestamps": [list(t) for t in c.timestamps]}
                for c in result.conditions
            ],
            "reviewer_brief_status": brief_status,
            "reviewer_brief": brief_body,
            "brief_violations": list(brief.get("violations", [])) if brief else [],
        },
    }
    if include_text:
        out["question_text"] = result.question_text
    return out


def recording_payload(recording_id: str, fragments: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for f in fragments:
        s = f["followup_pattern"]["status"]
        counts[s] = counts.get(s, 0) + 1
    return {"schema": SCHEMA, "recording_id": recording_id, "disclaimer": DISCLAIMER,
            "status_counts": counts, "answers": fragments}
