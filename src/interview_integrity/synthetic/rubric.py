"""Blind content rubric scored by an LLM judge.

The judge is never asked whether a text was written by AI (LLMs are unreliable at that).
It scores four observable properties and must quote evidence from the answer. Both real
and synthetic answers are normalised to the same transcript format first (lowercase, no
punctuation, no fillers), so formatting differences cannot give the answer away.

``composite`` is fixed before any results: mean(genericness, 6 - specificity). It is not
fitted to data.
"""

from __future__ import annotations

import re
from typing import Any

from ..fusion.turns import FILLERS, tokenize

DIMENSIONS = ("specificity", "genericness", "on_topic", "spoken_style")

JUDGE_SYSTEM = """You rate one job-interview answer on four observable properties.
The answer is a transcript: lowercase, with punctuation and filler words (um, uh) removed.
Do not judge grammar, punctuation or formatting. Do not guess who or what produced it.

Score each property from 1 to 5 and quote 1-3 short phrases (3-12 words) copied exactly
from the answer as evidence.
- specificity: 1 = no concrete details; 5 = many concrete, checkable details (names,
  numbers, dates, places, specific actions the speaker personally took).
- genericness: 1 = clearly this person's own story; 5 = could be said by almost anyone:
  template-like, textbook structure, stock interview phrases.
- on_topic: 1 = does not answer the question; 5 = directly answers it.
- spoken_style: 1 = reads like polished written prose; 5 = sounds like unplanned speech
  (restarts, asides, loose sentence structure).

Reply with JSON only:
{"specificity": {"score": 1, "evidence": ["..."]}, "genericness": {...},
 "on_topic": {...}, "spoken_style": {...}}"""


def normalize_for_scoring(text: str) -> str:
    """Shared transcript format: lowercase tokens, fillers and punctuation removed."""
    t = re.sub(r"\[[^\]]{0,40}\]", " ", text)
    return " ".join(tok for tok in tokenize(t) if tok not in FILLERS)


def build_judge_prompt(question: str, answer: str) -> str:
    return f"Interview question: {question.strip()}\n\nAnswer transcript:\n{normalize_for_scoring(answer)}"


def _quote_ok(quote: str, answer_norm: str) -> bool:
    q = normalize_for_scoring(quote)
    return bool(q) and f" {q} " in f" {answer_norm} "


def validate_rubric(obj: Any, answer: str) -> tuple[dict[str, int] | None, float | None, list[str]]:
    """Return (scores, share of evidence quotes found verbatim, problems).

    Scores are None when any dimension is missing or out of range. Quotes that are not in
    the answer are reported (a hallucination check) but do not void the scores.
    """
    if not isinstance(obj, dict):
        return None, None, ["not a JSON object"]
    norm = normalize_for_scoring(answer)
    scores, problems, quotes = {}, [], []
    for dim in DIMENSIONS:
        item = obj.get(dim)
        score = item.get("score") if isinstance(item, dict) else None
        if isinstance(score, float) and score.is_integer():
            score = int(score)
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            problems.append(f"{dim}: invalid score {score!r}")
            continue
        scores[dim] = score
        ev = item.get("evidence", [])
        if isinstance(ev, list):
            quotes += [q for q in ev if isinstance(q, str)]
    found = [_quote_ok(q, norm) for q in quotes]
    if found and not all(found):
        problems.append(f"{found.count(False)} evidence quote(s) not found in the answer")
    if len(scores) != len(DIMENSIONS):
        return None, (sum(found) / len(found)) if found else None, problems
    return scores, (sum(found) / len(found)) if found else None, problems


def composite(scores: dict[str, int]) -> float:
    """Content signal fixed a priori: high genericness and low specificity -> higher value."""
    return (scores["genericness"] + (6 - scores["specificity"])) / 2
