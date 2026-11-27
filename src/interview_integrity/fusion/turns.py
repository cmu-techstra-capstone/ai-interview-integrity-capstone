"""Speaker turns and answer windows.

The MIT transcripts are speaker-labelled (Interviewer / Interviewee) but have no
timestamps. ASR gives timestamps but no speakers. ``align_turns`` maps ASR words onto
the labelled transcript with a token-level sequence alignment, so every turn gets a
start/end time and a coverage figure that says how much of it was actually matched.
Poorly matched windows are marked ``timing_ok=False``; downstream code abstains on them
instead of guessing.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

INTERVIEWER = "interviewer"
INTERVIEWEE = "interviewee"

FILLERS = frozenset({
    "um", "umm", "uhm", "uh", "uhh", "ah", "ahh", "er", "erm", "eh", "hmm", "hm",
    "mm", "mhm", "mhmm", "mmhmm", "mhhmm", "uhum",
})

_SPEAKER_RE = re.compile(r"^\s*(interviewer|interviewee)\s*:\s*", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens; apostrophes are dropped so "I'm" and "Im" match."""
    return _TOKEN_RE.findall(text.lower().replace("'", "").replace("’", ""))


def content_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in FILLERS]


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class TimedTurn:
    speaker: str
    text: str
    start: float | None
    end: float | None
    coverage: float  # fraction of the turn's tokens matched to ASR words
    first_edge_matched: bool  # one of the first 3 tokens matched (reliable start)
    last_edge_matched: bool  # one of the last 3 tokens matched (reliable end)
    words: tuple[Word, ...] = ()  # ASR words matched to this turn, in time order


@dataclass(frozen=True)
class AnswerWindow:
    question_id: str
    question_text: str
    question_end: float | None
    answer_start: float | None
    answer_end: float | None
    answer_text: str
    answer_words: tuple[Word, ...] = field(default=())
    timing_ok: bool = False
    timing_note: str = ""

    @property
    def latency(self) -> float | None:
        if self.question_end is None or self.answer_start is None:
            return None
        return self.answer_start - self.question_end


def parse_turker_transcript(text: str) -> list[Turn]:
    """Parse ``Interviewer: ...|Interviewee: ...`` into turns.

    A segment without a speaker prefix is appended to the previous turn. Consecutive
    segments from the same speaker are merged.
    """
    turns: list[Turn] = []
    for raw in text.split("|"):
        seg = raw.strip()
        if not seg:
            continue
        m = _SPEAKER_RE.match(seg)
        if m:
            speaker, body = m.group(1).lower(), seg[m.end():].strip()
        elif turns:
            speaker, body = turns[-1].speaker, seg
        else:
            continue
        if turns and turns[-1].speaker == speaker:
            turns[-1] = Turn(speaker, f"{turns[-1].text} {body}".strip())
        elif body:
            turns.append(Turn(speaker, body))
    return turns


def align_turns(turns: list[Turn], words: list[Word]) -> list[TimedTurn]:
    """Give each labelled turn a time span by aligning its tokens to ASR words."""
    ref: list[tuple[int, str]] = [(i, tok) for i, t in enumerate(turns) for tok in tokenize(t.text)]
    hyp: list[tuple[int, str]] = []  # (word index, token)
    for wi, w in enumerate(words):
        for tok in tokenize(w.text):
            hyp.append((wi, tok))
    matcher = difflib.SequenceMatcher(None, [t for _, t in ref], [t for _, t in hyp], autojunk=False)
    ref_to_word: dict[int, int] = {}
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            ref_to_word[a + k] = hyp[b + k][0]

    per_turn: dict[int, list[int]] = {}
    for pos, (ti, _) in enumerate(ref):
        per_turn.setdefault(ti, []).append(pos)

    out: list[TimedTurn] = []
    for ti, turn in enumerate(turns):
        positions = per_turn.get(ti, [])
        matched = [p for p in positions if p in ref_to_word]
        widx = sorted({ref_to_word[p] for p in matched})
        tw = tuple(words[i] for i in widx)
        out.append(TimedTurn(
            speaker=turn.speaker, text=turn.text,
            start=min((w.start for w in tw), default=None),
            end=max((w.end for w in tw), default=None),
            coverage=(len(matched) / len(positions)) if positions else 0.0,
            first_edge_matched=any(p in ref_to_word for p in positions[:3]),
            last_edge_matched=any(p in ref_to_word for p in positions[-3:]),
            words=tw,
        ))
    return out


def is_question_turn(turn: TimedTurn | Turn, min_content_tokens: int = 4) -> bool:
    """A substantive interviewer turn; short acknowledgements ("mhhmm", "ok great") are not."""
    return turn.speaker == INTERVIEWER and len(content_tokens(turn.text)) >= min_content_tokens


def build_answer_windows(turns: list[TimedTurn], min_coverage: float = 0.5,
                         max_negative_latency: float = 0.5) -> list[AnswerWindow]:
    """One window per substantive question followed by an interviewee answer.

    Short interviewer backchannels inside an answer stay part of that answer. Timing is
    trusted only when the end of the question and the start of the answer were matched
    and both turns reach ``min_coverage``.
    """
    windows: list[AnswerWindow] = []
    i, qn = 0, 0
    while i < len(turns):
        q = turns[i]
        if not is_question_turn(q):
            i += 1
            continue
        j = i + 1
        answer: list[TimedTurn] = []
        while j < len(turns) and not is_question_turn(turns[j]):
            if turns[j].speaker == INTERVIEWEE:
                answer.append(turns[j])
            j += 1
        if answer:
            qn += 1
            first, last = answer[0], answer[-1]
            notes = []
            if q.coverage < min_coverage or not q.last_edge_matched or q.end is None:
                notes.append("question end not reliably aligned")
            if first.coverage < min_coverage or not first.first_edge_matched or first.start is None:
                notes.append("answer start not reliably aligned")
            if q.end is not None and first.start is not None and first.start - q.end < -max_negative_latency:
                notes.append("answer starts before question ends (overlap or misalignment)")
            words = tuple(sorted({w for t in answer for w in t.words}, key=lambda w: (w.start, w.end)))
            ends = [t.end for t in answer if t.end is not None]
            windows.append(AnswerWindow(
                question_id=f"q{qn:02d}", question_text=q.text,
                question_end=q.end, answer_start=first.start,
                answer_end=max(ends) if ends else None,
                answer_text=" ".join(t.text for t in answer),
                answer_words=words, timing_ok=not notes, timing_note="; ".join(notes),
            ))
        i = j
    return windows
