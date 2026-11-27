"""Reviewer brief: turn one deterministic follow-up result into plain language with an LLM.

The LLM never decides anything. It receives the already-computed conditions (numbers,
timestamps, question text) and writes a short note: what was measured, other ordinary
explanations, and 1-3 follow-up questions. ``validate_brief`` rejects any output that
states a verdict, gives a probability, or cites a time that is not in the input.

Only measurements and the interviewer's question are sent by default. The candidate's
answer text is sent only when ``include_answer_text=True``, which needs team/client
approval because it sends interview content to an external model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..llm.base import LLMClient
from .followup import SUGGEST, FollowupResult

SYSTEM_PROMPT = """You help a human interviewer review a recorded job interview.
You receive measurements that a deterministic rule computed for ONE answer. The rule
("delayed start + look-away + fluent answer") is unvalidated and was not trained on any
real AI-assistance data.

Rules:
- Describe only what was measured. Never say or imply that the candidate cheated, lied,
  used AI, read from a script, or is dishonest. Never give a probability, percentage,
  likelihood, score or verdict.
- Always give ordinary explanations (for example: thinking before answering, looking at
  notes or a resume, looking at the interviewer, camera angle, rehearsed answer, network lag).
- Cite only timestamps that appear in the input, in seconds.
- Suggest 1-3 short, neutral follow-up questions that let the candidate show their own
  understanding (ask for a specific example, a detail, a trade-off, or "why").
- Reply with JSON only, matching this shape:
{"summary": str, "observations": [{"text": str, "timestamps": [[start, end], ...]}],
 "alternative_explanations": [str, ...], "suggested_followup_questions": [str, ...],
 "limitations": [str, ...]}"""

BANNED = re.compile(
    r"\b(cheat\w*|dishonest\w*|lying|lied|liar|guilty|fraud\w*|ai[- ]generated|"
    r"used (an )?ai|using (an )?ai|chatgpt|read(ing)? from a script|probabilit\w*|likelihood|"
    r"confidence score|verdict)\b|\d+(\.\d+)?\s*%",
    re.IGNORECASE,
)
REQUIRED_KEYS = ("summary", "observations", "alternative_explanations", "suggested_followup_questions", "limitations")


def brief_payload(result: FollowupResult, answer_text: str | None = None) -> dict[str, Any]:
    payload = {
        "question_id": result.question_id,
        "rule_status": result.status,
        "question_text": result.question_text,
        "question_end_s": result.question_end,
        "answer_start_s": result.answer_start,
        "answer_end_s": result.answer_end,
        "conditions": [
            {"name": c.name, "required": c.required, "status": c.status, "value": c.value,
             "threshold": c.threshold, "measured": c.explanation,
             "timestamps": [list(t) for t in c.timestamps]}
            for c in result.conditions
        ],
    }
    if answer_text is not None:
        payload["answer_text"] = answer_text
    return payload


def build_messages(result: FollowupResult, answer_text: str | None = None,
                   include_answer_text: bool = False) -> tuple[str, str]:
    if result.status != SUGGEST:
        raise ValueError("Briefs are only written for answers where the rule suggests a follow-up.")
    payload = brief_payload(result, answer_text if include_answer_text else None)
    return SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False, indent=2)


def _allowed_times(result: FollowupResult) -> list[float]:
    times = [t for t in (result.question_end, result.answer_start, result.answer_end) if t is not None]
    for c in result.conditions:
        for s, e in c.timestamps:
            times += [s, e]
    return times


def _strings(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v)]
    return []


def validate_brief(brief: Any, result: FollowupResult, tolerance_s: float = 0.6) -> list[str]:
    """Return a list of violations; an empty list means the brief may be shown."""
    if not isinstance(brief, dict):
        return ["brief is not a JSON object"]
    problems = [f"missing key: {k}" for k in REQUIRED_KEYS if k not in brief]
    for text in _strings(brief):
        m = BANNED.search(text)
        if m:
            problems.append(f"banned wording: {m.group(0)!r}")
    qs = brief.get("suggested_followup_questions", [])
    if not isinstance(qs, list) or not 1 <= len(qs) <= 3:
        problems.append("suggested_followup_questions must contain 1-3 items")
    if not brief.get("alternative_explanations"):
        problems.append("alternative_explanations must not be empty")
    allowed = _allowed_times(result)
    for obs in brief.get("observations", []) or []:
        for span in (obs.get("timestamps", []) if isinstance(obs, dict) else []):
            for t in span if isinstance(span, (list, tuple)) else [span]:
                if not isinstance(t, (int, float)) or not any(abs(t - a) <= tolerance_s for a in allowed):
                    problems.append(f"timestamp not in input: {t!r}")
    return problems


def parse_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?\s*|\s*```$", "", text)
    return json.loads(text)


def generate_brief(client: LLMClient, result: FollowupResult, *, model: str,
                   answer_text: str | None = None, include_answer_text: bool = False) -> dict[str, Any]:
    """Call the LLM once; return ``{"brief", "violations", "accepted"}``.

    A brief with violations is returned with ``accepted=False`` and must not be shown.
    """
    system, user = build_messages(result, answer_text, include_answer_text)
    resp = client.generate(user, model=model, system=system, temperature=0.2, max_tokens=700)
    try:
        brief = parse_json(resp.text)
    except (json.JSONDecodeError, ValueError):
        return {"brief": None, "violations": ["response is not valid JSON"], "accepted": False, "model": resp.model}
    violations = validate_brief(brief, result)
    return {"brief": brief, "violations": violations, "accepted": not violations, "model": resp.model}
