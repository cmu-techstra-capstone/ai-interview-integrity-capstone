"""Find known interview questions inside an ASR transcript (no speaker labels needed).

For self-recorded tests and simple demos: the questions are read aloud from a list, so the
recording has one speaker and no labelled transcript. Each question is matched, in order, to the
best-fitting run of ASR words (tolerant of recognition errors). Words between one question and
the next are treated as the candidate's answer. Questions that cannot be found are reported and
skipped, never guessed.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path

from .turns import INTERVIEWEE, INTERVIEWER, TimedTurn, Word, tokenize


@dataclass(frozen=True)
class LocatedQuestion:
    index: int
    question: str
    found: bool
    match_ratio: float
    start: float | None = None
    end: float | None = None


def load_questions(path: str | Path) -> list[str]:
    """One question per line (blank lines and lines starting with # ignored), or a JSON list."""
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        qs = json.loads(raw)
        if not isinstance(qs, list) or not all(isinstance(q, str) for q in qs):
            raise ValueError("JSON questions file must be a list of strings")
    else:
        qs = [line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not qs:
        raise ValueError(f"no questions in {p}")
    return qs


def _best_window(q: list[str], hyp: list[str], start: int) -> tuple[float, int, int]:
    """Best (ratio, begin, end) over windows near the question's length, from ``start`` onwards."""
    n = len(q)
    best = (0.0, -1, -1)
    lengths = sorted({max(1, n + d) for d in (-2, -1, 0, 1, 2)})
    for s in range(start, len(hyp)):
        for length in lengths:
            e = s + length
            if e > len(hyp):
                break
            r = difflib.SequenceMatcher(None, q, hyp[s:e], autojunk=False).ratio()
            if r > best[0]:
                best = (r, s, e)
    return best


def locate_questions(questions: list[str], words: list[Word], min_ratio: float = 0.6
                     ) -> tuple[list[TimedTurn], list[LocatedQuestion]]:
    """Return speaker turns built from ASR words, plus where each question was found."""
    hyp: list[str] = []
    owner: list[int] = []  # token -> word index
    for wi, w in enumerate(words):
        for tok in tokenize(w.text):
            hyp.append(tok)
            owner.append(wi)

    located: list[LocatedQuestion] = []
    spans: list[tuple[int, int, int]] = []  # (question index, first word, last word)
    pos = 0
    for qi, q in enumerate(questions):
        qt = tokenize(q)
        ratio, s, e = _best_window(qt, hyp, pos) if qt else (0.0, -1, -1)
        if ratio < min_ratio:
            located.append(LocatedQuestion(qi, q, False, round(ratio, 3)))
            continue
        first, last = owner[s], owner[e - 1]
        spans.append((qi, first, last))
        located.append(LocatedQuestion(qi, q, True, round(ratio, 3), words[first].start, words[last].end))
        pos = e

    turns: list[TimedTurn] = []
    for k, (qi, first, last) in enumerate(spans):
        qwords = tuple(words[first:last + 1])
        turns.append(TimedTurn(INTERVIEWER, questions[qi], qwords[0].start, qwords[-1].end, 1.0, True, True, qwords))
        nxt = spans[k + 1][1] if k + 1 < len(spans) else len(words)
        awords = tuple(words[last + 1:nxt])
        if awords:
            turns.append(TimedTurn(INTERVIEWEE, " ".join(w.text for w in awords), awords[0].start, awords[-1].end,
                                   1.0, True, True, awords))
    return turns, located
