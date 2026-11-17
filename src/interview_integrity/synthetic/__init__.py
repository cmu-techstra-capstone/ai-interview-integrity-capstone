"""Synthetic AI-assisted answers and content-rubric scoring (research only).

There are no real AI-assisted interviews yet. This package builds a *partial* substitute
for the text/content channel only: AI-written answers to the same standardised MIT
questions, compared with the real students' answers. It cannot simulate gaze, timing or
voice, and synthetic labels are never mixed with real ``assistance_label`` values.
See ``docs/synthetic-positives.md``.
"""

from .generate import CONDITIONS, build_generation_prompt, build_profile, clean_generation, target_words
from .metrics import auroc, grouped_bootstrap_auroc
from .questions import QAPair, participant_of, qa_pairs, question_type
from .rubric import DIMENSIONS, JUDGE_SYSTEM, build_judge_prompt, composite, normalize_for_scoring, validate_rubric

__all__ = [
    "CONDITIONS", "DIMENSIONS", "JUDGE_SYSTEM", "QAPair", "auroc", "build_generation_prompt",
    "build_judge_prompt", "build_profile", "clean_generation", "composite", "grouped_bootstrap_auroc",
    "normalize_for_scoring", "participant_of", "qa_pairs", "question_type", "target_words", "validate_rubric",
]
