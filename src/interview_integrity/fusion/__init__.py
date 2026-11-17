"""Timeline fusion: align question/answer turns with visual events and describe a
predefined *follow-up pattern* for human review.

Nothing here estimates whether a candidate used AI. The pattern is a hand-written,
unvalidated rule ("delayed start + look-away + fluent answer") that only suggests where
an interviewer might ask a follow-up question. See ``docs/followup-pattern.md``.
"""

from .followup import (
    ConditionResult,
    FollowupConfig,
    FollowupResult,
    VisualTrack,
    evaluate_interview,
    evaluate_window,
)
from .turns import AnswerWindow, TimedTurn, Turn, Word, align_turns, build_answer_windows, parse_turker_transcript

__all__ = [
    "AnswerWindow", "ConditionResult", "FollowupConfig", "FollowupResult", "TimedTurn", "Turn",
    "VisualTrack", "Word", "align_turns", "build_answer_windows", "evaluate_interview",
    "evaluate_window", "parse_turker_transcript",
]
