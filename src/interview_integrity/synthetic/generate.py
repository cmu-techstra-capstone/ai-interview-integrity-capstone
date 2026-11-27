"""Prompts for controlled AI-written interview answers.

Each condition imitates what a candidate might type into a chatbot during an interview.
The labels mirror the staged-interview protocol but are stored as
``synthetic_condition``, never as a real ``assistance_label``.

- ``AI_VERBATIM``: generic answer, no personal context, read out as written.
- ``AI_PERSONALIZED``: the candidate pastes some of their own background first.
- ``AI_SPOKEN``: personalised and asked to sound unplanned and conversational (the
  hardest case for any content signal).

Length is matched to the real answer to the same question, so length alone cannot
separate real from synthetic.
"""

from __future__ import annotations

import re

from ..fusion.turns import tokenize
from .questions import QAPair

GENERATION_SYSTEM = "You are a helpful assistant."  # mimic a default chatbot session

CONDITIONS = ("AI_VERBATIM", "AI_PERSONALIZED", "AI_SPOKEN")

_BASE = ("I'm a college student in a job interview for an internship right now and need help fast. "
         "The interviewer just asked me: \"{question}\"\n")
_TEMPLATES = {
    "AI_VERBATIM": _BASE + "Write the answer I should say, about {words} words, in first person. "
                           "Reply with only the answer.",
    "AI_PERSONALIZED": ("Some background about me: {profile}\n\n" + _BASE +
                        "Write the answer I should say using my background, about {words} words, in first "
                        "person. Reply with only the answer."),
    "AI_SPOKEN": ("Some background about me: {profile}\n\n" + _BASE +
                  "Write what I should say using my background, about {words} words, in first person. Make it "
                  "sound like I'm speaking naturally off the top of my head: casual, a bit loose, not polished "
                  "or essay-like. Reply with only the words I'd say."),
}


def target_words(real_words: int, lo: int = 40, hi: int = 250) -> int:
    return int(min(hi, max(lo, round(real_words / 10) * 10)))


def build_profile(pairs: list[QAPair], exclude: QAPair, max_words: int = 120) -> str:
    """Background the candidate would paste: their own self-introduction, else other answers.

    The target answer itself is always excluded, so its content is never handed to the
    generator.
    """
    others = [p for p in pairs if p.participant_id == exclude.participant_id
              and (p.recording_id, p.question_id) != (exclude.recording_id, exclude.question_id)]
    intro = [p for p in others if p.question_type == "about_yourself"]
    pool = intro or sorted(others, key=lambda p: -p.n_words)
    words = " ".join(p.answer_text for p in pool).split()
    return " ".join(words[:max_words])


def build_generation_prompt(pair: QAPair, condition: str, profile: str = "") -> str:
    if condition not in _TEMPLATES:
        raise ValueError(f"unknown condition {condition!r}")
    if condition != "AI_VERBATIM" and not profile.strip():
        raise ValueError(f"{condition} needs a profile")
    return _TEMPLATES[condition].format(question=pair.question_text.strip(), profile=profile.strip(),
                                        words=target_words(pair.n_words))


_PREAMBLE = re.compile(r"^(sure|certainly|of course|absolutely|here('s| is)|okay|ok)\b[^\n]{0,80}[:!]\s*\n+", re.IGNORECASE)


def clean_generation(text: str) -> str:
    """Strip chat wrappers (preambles, quotes, markdown) so only the spoken words remain."""
    t = text.strip()
    t = _PREAMBLE.sub("", t)
    t = re.sub(r"^\s*(\*\*)?answer:?(\*\*)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[*_#>`]+", "", t)
    t = re.sub(r"\[[^\]]{0,40}\]", " ", t)  # stage directions like [pause]
    t = t.strip().strip('"“”').strip()
    return re.sub(r"\s+", " ", t)


def word_count(text: str) -> int:
    return len(tokenize(text))
