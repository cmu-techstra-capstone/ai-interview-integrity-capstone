"""Question/answer pairs and question types from the MIT speaker-labelled transcripts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from ..fusion.turns import INTERVIEWEE, content_tokens, is_question_turn, parse_turker_transcript

# Checked in order; first match wins. MIT counsellors used a fixed question list.
QUESTION_TYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("change_one_thing", (r"change one thing", r"change (any|one) thing about yourself")),
    ("weakness", (r"weakness",)),
    ("conflict", (r"conflict",)),
    ("team_challenge", (r"team.*challenge", r"challenge.*team", r"solve (that|the) problem")),
    ("leadership", (r"leader",)),
    ("why_hire", (r"hire you", r"get (this|the) job", r"have this job", r"choose you")),
    ("about_yourself", (r"about yourself", r"your background")),
    ("smalltalk", (r"how are you", r"how('s| is) it going", r"thank(s| you) for coming")),
)
EVALUATED_TYPES = ("about_yourself", "leadership", "team_challenge", "conflict", "weakness",
                   "change_one_thing", "why_hire")


def question_type(text: str) -> str:
    t = text.lower()
    for name, patterns in QUESTION_TYPES:
        if any(re.search(p, t) for p in patterns):
            return name
    return "other"


def participant_of(recording_id: str) -> tuple[str, str]:
    """``P12`` -> (``P12``, ``pre``); ``PP12`` -> (``P12``, ``post``)."""
    m = re.fullmatch(r"(pp?)(\d+)", recording_id.strip().lower())
    if not m:
        raise ValueError(f"not an MIT recording id: {recording_id!r}")
    return f"P{m.group(2)}", "pre" if m.group(1) == "p" else "post"


@dataclass(frozen=True)
class QAPair:
    participant_id: str
    recording_id: str
    session: str
    question_id: str
    question_type: str
    question_text: str
    answer_text: str
    n_words: int

    def to_dict(self) -> dict:
        return asdict(self)


def qa_pairs(recording_id: str, transcript: str) -> list[QAPair]:
    """Same windowing as ``fusion.turns.build_answer_windows`` (so question ids match), untimed."""
    pid, session = participant_of(recording_id)
    turns = parse_turker_transcript(transcript)
    out, i, qn = [], 0, 0
    while i < len(turns):
        if not is_question_turn(turns[i]):
            i += 1
            continue
        j, answer = i + 1, []
        while j < len(turns) and not is_question_turn(turns[j]):
            if turns[j].speaker == INTERVIEWEE:
                answer.append(turns[j].text)
            j += 1
        if answer:
            qn += 1
            text = " ".join(answer)
            out.append(QAPair(pid, recording_id, session, f"q{qn:02d}", question_type(turns[i].text),
                              turns[i].text.strip(), text, len(content_tokens(text))))
        i = j
    return out
