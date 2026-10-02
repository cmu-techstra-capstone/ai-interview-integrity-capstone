"""Extension point for additional feature extractors (e.g. future visual features).

Teammates can add extractors without touching the core pipeline:

    class MyVisualExtractor:
        name = "visual_example"       # feature names must start with ``prefix``
        prefix = "visual_"
        def extract(self, ctx: AnswerContext) -> dict[str, Any]:
            ...read ctx.video_path between ctx.answer_start and ctx.answer_end...
            return {"visual_example_value": 1.0}

    process_video(video, metadata, config=PipelineConfig(extractors=[MyVisualExtractor()]))

Extractors receive local file paths for the duration of one answer and must not
modify them. Unavailable values should be ``None``, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..transcription.base import Transcript


@dataclass(frozen=True)
class AnswerContext:
    video_path: Path
    audio_path: Path
    recording_id: str
    question_id: str
    answer_start: float | None
    answer_end: float | None
    question_start: float | None
    question_end: float | None
    transcript: Transcript | None  # answer-window transcript, if any
    speech_intervals: tuple[tuple[float, float], ...]


@runtime_checkable
class FeatureExtractor(Protocol):
    name: str
    prefix: str

    def extract(self, ctx: AnswerContext) -> dict[str, Any]: ...


class FeatureExtractorError(ValueError):
    pass


def run_extractor(extractor: FeatureExtractor, ctx: AnswerContext, reserved: set[str]) -> dict[str, Any]:
    out = extractor.extract(ctx)
    if not isinstance(out, dict):
        raise FeatureExtractorError(f"{extractor.name}: extract() must return a dict")
    bad_prefix = [k for k in out if not k.startswith(extractor.prefix)]
    if bad_prefix:
        raise FeatureExtractorError(f"{extractor.name}: features must start with {extractor.prefix!r}: {bad_prefix}")
    clash = set(out) & reserved
    if clash:
        raise FeatureExtractorError(f"{extractor.name}: feature names already used: {sorted(clash)}")
    return out
