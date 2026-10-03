"""End-to-end processing of one interview video into structured dataset rows.

    video -> ingest (probe, checksum, audio.wav, audio validation) -> transcript (optional)
      -> per-question answer window -> speech intervals (word timestamps or VAD)
      -> linguistic + timing + loudness + recording-quality features
      -> optional plug-in extractors (e.g. future visual features)
      -> validated InterviewSample(s)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audio.vad import frame_levels, speech_intervals_from_levels, speech_threshold
from .datasets.schema import QuestionSpec, RecordingMetadata, SchemaError, InterviewSample
from .features.base import AnswerContext, FeatureExtractor, run_extractor
from .features.linguistic import SimilarityScorer, extract_linguistic_features
from .features.loudness import extract_loudness_features
from .features.timing import DEFAULT_MIN_PAUSE, compute_timing_features, speech_intervals_from_words
from .ingestion.video import IngestedVideo, ingest_video
from .transcription.base import Transcriber, Transcript


TIMING_TOLERANCE_S = 0.5  # container/codec durations differ slightly from metadata


def _check_within_recording(q: QuestionSpec, duration: float | None, recording_id: str) -> None:
    """Fail fast on metadata timestamps that cannot belong to this recording."""
    if duration is None:
        return
    for name in ("question_start", "question_end", "answer_start", "answer_end"):
        value = getattr(q, name)
        if value is not None and value > duration + TIMING_TOLERANCE_S:
            raise SchemaError(
                f"Recording {recording_id}, question {q.question_id}: {name}={value}s is beyond the "
                f"recording's audio duration ({duration:.2f}s). Check the metadata timestamps."
            )
    if q.question_end is not None and q.answer_end is not None and q.question_end > q.answer_end:
        raise SchemaError(
            f"Recording {recording_id}, question {q.question_id}: question_end ({q.question_end}) "
            f"is after answer_end ({q.answer_end})."
        )


@dataclass
class PipelineConfig:
    interim_dir: Path = Path("data/interim")
    min_pause: float = DEFAULT_MIN_PAUSE
    vad_threshold_dbfs: float | None = None  # None = adaptive per recording
    overwrite: bool = False
    extractors: list[FeatureExtractor] = field(default_factory=list)


def _answer_transcript(transcript: Transcript | None, q: QuestionSpec, multi: bool) -> Transcript | None:
    if transcript is None:
        return None
    has_window = q.answer_start is not None and q.answer_end is not None
    if not has_window:
        return transcript
    if transcript.has_word_timestamps or transcript.has_segment_timestamps:
        return transcript.window(q.answer_start, q.answer_end)  # type: ignore[arg-type]
    if multi:
        raise SchemaError(
            "Transcript has no timestamps, so it cannot be split across multiple questions. "
            "Provide a timestamped transcript or one video per answer."
        )
    return transcript  # single answer: assume the transcript covers it


def _process_question(
    ingested: IngestedVideo,
    q: QuestionSpec,
    transcript: Transcript | None,
    transcript_path: Path | None,
    config: PipelineConfig,
    similarity_scorer: SimilarityScorer | None,
) -> InterviewSample:
    meta = ingested.metadata
    multi = len(meta.questions) > 1
    if multi and (q.answer_start is None or q.answer_end is None):
        raise SchemaError(
            f"Recording {meta.recording_id} has {len(meta.questions)} questions; "
            f"question {q.question_id} needs answer_start and answer_end."
        )

    _check_within_recording(q, ingested.audio.duration, meta.recording_id)
    answer_tr = _answer_transcript(transcript, q, multi)
    # Search for the answer after the question ends, so the interviewer's speech is not
    # mistaken for the start of the answer.
    if q.answer_start is not None:
        window_start = q.answer_start
    elif q.question_end is not None:
        window_start = q.question_end
    else:
        window_start = 0.0
    window_end = q.answer_end if q.answer_end is not None else ingested.audio.duration
    if answer_tr is not None and q.answer_start is None and q.question_end is not None and answer_tr.has_word_timestamps:
        answer_tr = answer_tr.window(window_start, window_end if window_end is not None else float("inf"))

    levels = frame_levels(ingested.audio.path, start=window_start, end=window_end)
    if answer_tr is not None and answer_tr.words and answer_tr.has_word_timestamps:
        intervals = speech_intervals_from_words(answer_tr.words, merge_gap=config.min_pause)
        timing_source = "word_timestamps"
    else:
        threshold = speech_threshold(levels, threshold_dbfs=config.vad_threshold_dbfs)
        intervals = speech_intervals_from_levels(levels, threshold, merge_gap=config.min_pause)
        timing_source = "energy_vad"

    # Explicit metadata wins; otherwise the answer spans first-to-last detected speech.
    answer_start = q.answer_start if q.answer_start is not None else (intervals[0][0] if intervals else None)
    answer_end = q.answer_end if q.answer_end is not None else (intervals[-1][1] if intervals else None)

    text = answer_tr.text if answer_tr is not None else None
    linguistic = extract_linguistic_features(
        text, question_text=q.question_text, similarity_scorer=similarity_scorer
    )
    if answer_tr is None:
        linguistic = {k: None for k in linguistic}

    timing = compute_timing_features(
        speech_intervals=intervals,
        answer_start=answer_start,
        answer_end=answer_end,
        question_end=q.question_end,
        word_count=linguistic["word_count"],
        words=answer_tr.words if answer_tr is not None and answer_tr.has_word_timestamps else None,
        min_pause=config.min_pause,
    )
    answer_duration = timing.pop("answer_duration")
    response_latency = timing.pop("response_latency")

    features: dict[str, Any] = {
        **linguistic,
        **timing,
        **extract_loudness_features(levels, intervals),
        **ingested.audio_quality.to_features(),
        "timing_source": timing_source,
        "transcript_source": answer_tr.provider if answer_tr is not None else None,
    }

    if config.extractors:
        ctx = AnswerContext(
            video_path=Path(ingested.video.path),
            audio_path=Path(ingested.audio.path),
            recording_id=meta.recording_id,
            question_id=q.question_id,
            answer_start=answer_start,
            answer_end=answer_end,
            question_start=q.question_start,
            question_end=q.question_end,
            transcript=answer_tr,
            speech_intervals=tuple(intervals),
        )
        for extractor in config.extractors:
            reserved = set(features) | {"interview_id", "participant_id", "question_id"}
            features.update(run_extractor(extractor, ctx, reserved))

    return InterviewSample(
        interview_id=meta.interview_id,
        participant_id=meta.participant_id,
        question_id=q.question_id,
        source_dataset=meta.source_dataset,
        recording_id=meta.recording_id,
        augmentation=meta.augmentation,
        assistance_label=q.assistance_label,
        deception_label=q.deception_label,
        video_reference=ingested.video.path,
        video_sha256=ingested.video.sha256,
        audio_reference=ingested.audio.path,
        transcript_path=str(transcript_path) if transcript_path else None,
        question_text=q.question_text,
        transcript=text,
        question_start=q.question_start,
        question_end=q.question_end,
        answer_start=answer_start,
        answer_end=answer_end,
        response_latency=response_latency,
        answer_duration=answer_duration,
        ai_model_used=q.ai_model_used,
        ai_prompt_used=q.ai_prompt_used,
        generated_ai_answer=q.generated_ai_answer,
        response_notes=q.response_notes,
        features=features,
    ).validate()


def process_video(
    video_path: str | Path,
    metadata: RecordingMetadata | dict[str, Any] | str | Path,
    *,
    transcriber: Transcriber | None = None,
    config: PipelineConfig | None = None,
    similarity_scorer: SimilarityScorer | None = None,
) -> list[InterviewSample]:
    """Process one video into one ``InterviewSample`` per question in its metadata.

    With ``transcriber=None`` the pipeline still runs: linguistic features are
    ``None`` and timing features come from energy-based VAD.
    """
    config = config or PipelineConfig()
    ingested = ingest_video(video_path, metadata, config.interim_dir, overwrite=config.overwrite)

    transcript: Transcript | None = None
    transcript_path: Path | None = None
    if transcriber is not None:
        transcript = transcriber.transcribe(ingested.audio.path)
        transcript_path = ingested.work_dir / "transcript.json"
        transcript_path.write_text(json.dumps(transcript.to_dict(), indent=2))

    return [
        _process_question(ingested, q, transcript, transcript_path, config, similarity_scorer)
        for q in ingested.metadata.questions
    ]
