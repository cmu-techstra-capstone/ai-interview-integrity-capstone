"""Suggest follow-up questions for a human interviewer.

Two paths, so the demo never breaks on stage:
  1. LLM prompting (if ANTHROPIC_API_KEY or OPENROUTER_API_KEY is set; 15 s timeout).
  2. Offline template fallback driven by which signals fired.

The questions are depth probes (specifics, ownership, trade-offs, failure). They never accuse the
candidate; they simply give the interviewer a way to check hands-on experience.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

SYSTEM_PROMPT = (
    "You assist a HUMAN interviewer during a live interview. You are given the question, the "
    "candidate's answer, and weak automated signals that the answer may be generic or prepared. "
    "Write follow-up questions that let the interviewer check real, hands-on experience: ask for "
    "a specific project, the candidate's own role, a decision and its trade-off, something that "
    "went wrong, or a changed constraint. Rules: never accuse the candidate of cheating or mention "
    "AI detection; keep each question under 30 words, conversational, and answerable only by "
    "someone who actually did the work; make them specific to this answer, not generic. "
    'Reply with ONLY a JSON array of exactly 3 strings.'
)

# signal name -> (question template). {term} is filled from the answer when possible.
TEMPLATES = {
    "generic": "Can you walk me through one specific time you actually did this - the project, your role, and what went wrong?",
    "polish": "That was a clean summary. Which part of it did you personally find hardest, and what did you get wrong the first time?",
    "buzzwords": "You mentioned {term}. How would you explain that to a teammate who has never heard of it, using an example from your own work?",
    "spontaneity": "What's something you tried here that didn't work, and how did you find out?",
    "rhythm": "If your budget or time were cut in half, what would you drop first, and why?",
    "complete": "Pick the single most important point you made. What would you do differently if that point turned out to be wrong?",
    "uniform_cadence": "Can you put that in your own words again, starting from a concrete example you have lived through?",
    "few_pauses": "Let's go a level deeper on that. What would break first if the load or the team size doubled?",
    "fast_fluent": "Slow down for me here: what was the exact moment you realised this approach was right (or wrong)?",
    "latency": "What was the first thing that came to mind when I asked that, before you structured your answer?",
}
NEUTRAL = "Tell me about the most recent time you did exactly this. What was the outcome?"


def _pick_term(answer: str) -> str:
    from scoring import AI_WORDS  # local import keeps module import cheap

    low = answer.lower()
    for w in AI_WORDS:
        if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low):
            return w
    words = [w for w in re.findall(r"[A-Za-z]{7,}", answer)]
    return words[0].lower() if words else "that approach"


def template_followups(answer: str, signals: list[dict[str, Any]], n: int = 3) -> list[str]:
    fired = sorted((s for s in signals if s.get("fired")), key=lambda s: s["value"] * s["weight"], reverse=True)
    out: list[str] = []
    for s in fired:
        tpl = TEMPLATES.get(s["name"])
        if tpl:
            q = tpl.format(term=_pick_term(answer)) if "{term}" in tpl else tpl
            if q not in out:
                out.append(q)
        if len(out) == n:
            break
    for fallback in (NEUTRAL, TEMPLATES["generic"], TEMPLATES["rhythm"]):
        if len(out) >= n:
            break
        if fallback not in out:
            out.append(fallback)
    return out[:n]


def _build_prompt(question: str, answer: str, signals: list[dict[str, Any]], history: list[dict[str, str]]) -> str:
    fired = [f"- {s['label']}: {s['detail']}" for s in signals if s.get("fired")] or ["- (no strong signals)"]
    prior = "\n".join(f"Q: {h.get('question', '')}\nA: {h.get('answer', '')[:300]}" for h in history[-2:]) or "(none)"
    return (
        f"Earlier turns:\n{prior}\n\nCurrent question: {question or '(not provided)'}\n"
        f"Candidate answer: {answer}\n\nWeak signals noticed:\n" + "\n".join(fired) +
        "\n\nWrite 3 follow-up questions as a JSON array of strings."
    )


def _parse_json_list(text: str) -> list[str] | None:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    qs = [q.strip() for q in data if isinstance(q, str) and q.strip()]
    return qs[:3] or None


def _post(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https URLs)
        return json.loads(resp.read().decode())


def llm_followups(prompt: str) -> tuple[list[str] | None, str]:
    """Return (questions, provider_note). Never raises; (None, reason) means use the fallback."""
    model = os.environ.get("DEMO_LLM_MODEL")
    try:
        if os.environ.get("ANTHROPIC_API_KEY"):
            data = _post(
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
                {"model": model or "claude-sonnet-5-5", "max_tokens": 400, "temperature": 0.7,
                 "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": prompt}]},
            )
            text = "".join(b.get("text", "") for b in data.get("content", []))
            return _parse_json_list(text), "anthropic"
        if os.environ.get("OPENROUTER_API_KEY"):
            data = _post(
                "https://openrouter.ai/api/v1/chat/completions",
                {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "content-type": "application/json"},
                {"model": model or "anthropic/claude-sonnet-4.5", "max_tokens": 400, "temperature": 0.7,
                 "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]},
            )
            return _parse_json_list(data["choices"][0]["message"]["content"]), "openrouter"
        return None, "no API key set"
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
        return None, f"LLM call failed ({type(exc).__name__})"


def suggest(question: str, answer: str, signals: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    qs, note = llm_followups(_build_prompt(question, answer, signals, history or []))
    if qs:
        return {"questions": qs, "source": f"LLM prompt ({note})"}
    return {"questions": template_followups(answer, signals), "source": f"template fallback ({note})"}
