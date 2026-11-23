"""Simple, explainable linguistic features of an answer transcript.

These are research features, not an "AI-text detector". No single feature (or
combination) here is evidence that an answer was AI-assisted.

Caveat: many ASR systems (e.g. Whisper) drop disfluencies such as "um"/"uh",
so filler and self-correction counts depend heavily on the transcription source.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_SENTENCE_END_RE = re.compile(r"[.!?]+")

FILLED_PAUSES = frozenset({"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "mm"})
MULTIWORD_FILLERS: tuple[tuple[str, ...], ...] = (("you", "know"), ("i", "mean"))
# Ambiguous words that are often (not always) discourse fillers; counted separately.
DISCOURSE_MARKERS = frozenset({"like", "basically", "actually", "literally", "so", "well", "right"})
# Phrases that often signal a speaker repairing what they just said.
REPAIR_PHRASES: tuple[tuple[str, ...], ...] = (
    ("sorry",),
    ("i", "meant"),
    ("or", "rather"),
    ("no", "wait"),
    ("let", "me", "rephrase"),
    ("what", "i", "meant"),
)
STOPWORDS = frozenset(
    "a an and are as at be but by do does did for from have has how i if in is it its me my of on "
    "or our so that the their them then there these they this to was we were what when where which "
    "who why will with would you your can could should about tell describe".split()
)

MATTR_WINDOW = 50


class SimilarityScorer(Protocol):
    """Interface for question-answer semantic similarity (e.g. an embedding model).

    No implementation is bundled yet; choosing an embedding model is a pending decision.
    """

    name: str

    def score(self, question: str, answer: str) -> float: ...


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _count_phrase(tokens: list[str], phrase: tuple[str, ...]) -> int:
    n = len(phrase)
    return sum(1 for i in range(len(tokens) - n + 1) if tuple(tokens[i : i + n]) == phrase)


def _repetition_count(tokens: list[str]) -> int:
    """Immediate repeats of a word ("the the") or a word pair ("I think I think")."""
    content = [t for t in tokens if t not in FILLED_PAUSES]
    count = sum(1 for a, b in zip(content, content[1:]) if a == b)
    i = 0
    while i + 3 < len(content):
        if content[i] != content[i + 1] and content[i : i + 2] == content[i + 2 : i + 4]:
            count += 1
            i += 2
        else:
            i += 1
    return count


def _mattr(tokens: list[str], window: int = MATTR_WINDOW) -> float | None:
    """Moving-average type-token ratio: less length-sensitive than plain TTR."""
    if not tokens:
        return None
    if len(tokens) <= window:
        return len(set(tokens)) / len(tokens)
    ratios = [len(set(tokens[i : i + window])) / window for i in range(len(tokens) - window + 1)]
    return sum(ratios) / len(ratios)


def _sentences(text: str) -> list[str] | None:
    """Split on terminal punctuation; ``None`` if the text has none (e.g. unpunctuated ASR)."""
    if not _SENTENCE_END_RE.search(text):
        return None
    parts = _SENTENCE_END_RE.split(text)
    return [p for p in parts if tokenize(p)]


def _content_overlap(question: str, answer_tokens: list[str]) -> float | None:
    q = {t for t in tokenize(question) if t not in STOPWORDS}
    if not q:
        return None
    return len(q & set(answer_tokens)) / len(q)


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def extract_linguistic_features(
    text: str | None,
    *,
    question_text: str | None = None,
    similarity_scorer: SimilarityScorer | None = None,
) -> dict[str, Any]:
    """Compute baseline linguistic features. Returns ``None`` values where undefined."""
    text = text or ""
    tokens = tokenize(text)
    n = len(tokens)
    sentences = _sentences(text) if n else None

    filled = sum(1 for t in tokens if t in FILLED_PAUSES)
    multi = sum(_count_phrase(tokens, p) for p in MULTIWORD_FILLERS)
    fillers = filled + multi
    repetitions = _repetition_count(tokens)
    repairs = sum(_count_phrase(tokens, p) for p in REPAIR_PHRASES)

    semantic = None
    if similarity_scorer is not None and question_text and n:
        semantic = float(similarity_scorer.score(question_text, text))

    return {
        "word_count": n,
        "sentence_count": len(sentences) if sentences is not None else None,
        "avg_sentence_length": _round(n / len(sentences)) if sentences else None,
        "type_token_ratio": _round(len(set(tokens)) / n) if n else None,
        "mattr": _round(_mattr(tokens)),
        "filler_word_count": fillers,
        "filler_rate_per_100_words": _round(100 * fillers / n) if n else None,
        "discourse_marker_count": sum(1 for t in tokens if t in DISCOURSE_MARKERS),
        "repetition_count": repetitions,
        "self_correction_count": repetitions + repairs,
        "qa_content_word_overlap": _round(_content_overlap(question_text, tokens)) if question_text else None,
        "qa_semantic_similarity": _round(semantic),
    }
