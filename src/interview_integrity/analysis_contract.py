"""API-facing analysis contract shared with the Meet overlay TypeScript types.

Compatible with existing ``InterviewSample`` / ``EvidenceSignal`` / ``QualityIssue``
fields and the extension's ``DetectionResultState`` presentation types.

Does **not** fabricate model outputs or numerical cheating probabilities.
``EvidenceSignal`` descriptions are measurements, not proof of AI assistance.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .datasets.quality import QualityIssue
from .datasets.schema import InterviewSample
from .detection.boundary import DetectionInference
from .evidence import EvidenceSignal, describe_feature, modality_quality
from .features.registry import FEATURES, FeatureKind, split_by_kind
from .transcription.base import Transcript

ANALYSIS_SCHEMA_VERSION = "analysis.v1"

ProcessingState = Literal["completed", "completed_with_warnings", "failed"]
DataOrigin = Literal["offline_processing", "demo"]

# Behavioral features included as descriptive evidence when present on a sample.
DEFAULT_EVIDENCE_FEATURES: tuple[str, ...] = (
    "filler_word_count",
    "filler_rate_per_100_words",
    "word_count",
    "speech_rate_wpm",
    "articulation_rate_wpm",
    "pause_count",
    "long_pause_count",
    "mean_pause_duration",
    "pause_ratio",
    "speech_duration",
    "silence_duration",
    "type_token_ratio",
    "repetition_count",
)


@dataclass
class AnalysisProvenance:
    schema_version: str = ANALYSIS_SCHEMA_VERSION
    analysis_id: str = ""
    source: DataOrigin = "offline_processing"
    is_synthetic: bool = False
    transcript_mode: Literal["sidecar", "stt", "none"] = "none"
    stt_requested: str | None = None
    stt_options: dict[str, Any] = field(default_factory=dict)
    video_path: str | None = None
    metadata_ref: str | None = None
    transcript_path: str | None = None
    pipeline: str = "interview_integrity.services.analyze_offline_recording"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptSegmentRecord:
    id: str
    text: str
    start_seconds: float | None = None
    end_seconds: float | None = None
    speaker: str | None = None
    words: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnswerAnalysisRecord:
    interview_id: str
    participant_id: str
    question_id: str
    recording_id: str
    question_text: str | None
    transcript: str | None
    question_start: float | None
    question_end: float | None
    answer_start: float | None
    answer_end: float | None
    response_latency: float | None
    answer_duration: float | None
    transcript_segments: list[TranscriptSegmentRecord]
    has_word_timestamps: bool
    has_segment_timestamps: bool
    audio_timing_features: dict[str, Any]
    linguistic_features: dict[str, Any]
    recording_quality_features: dict[str, Any]
    provenance_features: dict[str, Any]
    evidence_signals: list[dict[str, Any]]
    sample_row: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["transcript_segments"] = [s.to_dict() if hasattr(s, "to_dict") else s for s in self.transcript_segments]
        return d


@dataclass
class OfflineAnalysisDocument:
    schema_version: str
    analysis_id: str
    processing_state: ProcessingState
    source: DataOrigin
    is_synthetic: bool
    provenance: AnalysisProvenance
    answers: list[AnswerAnalysisRecord]
    quality_issues: list[dict[str, Any]]
    detection: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    # Explicit: processing failure is not the same as detection unavailable.
    processing_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "analysis_id": self.analysis_id,
            "processing_state": self.processing_state,
            "source": self.source,
            "is_synthetic": self.is_synthetic,
            "provenance": self.provenance.to_dict(),
            "answers": [a.to_dict() for a in self.answers],
            "quality_issues": list(self.quality_issues),
            "detection": dict(self.detection),
            "errors": list(self.errors),
            "processing_error": self.processing_error,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def new_analysis_id() -> str:
    return f"anl_{uuid.uuid4().hex[:12]}"


def _load_transcript(path: str | Path | None) -> Transcript | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    if p.suffix.lower() == ".json":
        return Transcript.from_dict(json.loads(p.read_text()))
    text = p.read_text().strip()
    return Transcript.from_dict({"text": text, "provider": f"sidecar:{p.name}"}) if text else None


def _segments_for_answer(sample: InterviewSample, transcript: Transcript | None) -> tuple[list[TranscriptSegmentRecord], bool, bool]:
    if transcript is None:
        if (sample.transcript or "").strip():
            return (
                [
                    TranscriptSegmentRecord(
                        id=f"{sample.question_id}-full",
                        text=sample.transcript or "",
                        start_seconds=sample.answer_start,
                        end_seconds=sample.answer_end,
                        speaker="Candidate",
                    )
                ],
                False,
                sample.answer_start is not None and sample.answer_end is not None,
            )
        return [], False, False

    windowed = transcript
    if (
        sample.answer_start is not None
        and sample.answer_end is not None
        and (transcript.has_word_timestamps or transcript.has_segment_timestamps)
    ):
        try:
            windowed = transcript.window(sample.answer_start, sample.answer_end)
        except Exception:  # noqa: BLE001 — keep full transcript if windowing fails
            windowed = transcript

    records: list[TranscriptSegmentRecord] = []
    for i, seg in enumerate(windowed.segments):
        records.append(
            TranscriptSegmentRecord(
                id=f"{sample.question_id}-seg-{i}",
                text=seg.text,
                start_seconds=seg.start,
                end_seconds=seg.end,
                speaker=seg.speaker or "Candidate",
                words=[w.to_dict() for w in seg.words],
            )
        )
    if not records and (sample.transcript or "").strip():
        records.append(
            TranscriptSegmentRecord(
                id=f"{sample.question_id}-full",
                text=sample.transcript or "",
                start_seconds=sample.answer_start,
                end_seconds=sample.answer_end,
                speaker="Candidate",
            )
        )
    return records, windowed.has_word_timestamps, windowed.has_segment_timestamps


def build_evidence_for_sample(
    sample: InterviewSample,
    issues: list[QualityIssue] | None = None,
    feature_names: tuple[str, ...] = DEFAULT_EVIDENCE_FEATURES,
) -> list[EvidenceSignal]:
    """Descriptive behavioral EvidenceSignals only — never quality features as evidence."""
    quality = modality_quality(sample, issues)
    out: list[EvidenceSignal] = []
    for name in feature_names:
        if name not in FEATURES or FEATURES[name].kind is not FeatureKind.BEHAVIORAL:
            continue
        if name not in sample.features:
            continue
        # Skip nulls to avoid noisy "not measurable" clutter; missing stays implicit.
        if sample.features.get(name) is None:
            continue
        out.append(describe_feature(sample, name, quality))
    return out


def answer_record_from_sample(
    sample: InterviewSample,
    *,
    issues: list[QualityIssue] | None = None,
    evidence: list[EvidenceSignal] | None = None,
) -> AnswerAnalysisRecord:
    grouped = split_by_kind(sample.features)
    behavioral = grouped.get(FeatureKind.BEHAVIORAL, {})
    quality_feats = grouped.get(FeatureKind.QUALITY, {})
    provenance = grouped.get(FeatureKind.PROVENANCE, {})
    # Split behavioral into timing/audio vs linguistic by modality for the contract.
    audio_timing = {
        k: v
        for k, v in behavioral.items()
        if FEATURES.get(k) and FEATURES[k].modality.value in {"audio"}
    }
    linguistic = {
        k: v
        for k, v in behavioral.items()
        if FEATURES.get(k) and FEATURES[k].modality.value in {"transcript"}
    }
    # response_latency / answer_duration live on the sample, not always in features
    if sample.response_latency is not None:
        audio_timing = {**audio_timing, "response_latency": sample.response_latency}
    if sample.answer_duration is not None:
        audio_timing = {**audio_timing, "answer_duration": sample.answer_duration}

    tr = _load_transcript(sample.transcript_path)
    segments, has_words, has_segs = _segments_for_answer(sample, tr)
    signals = evidence if evidence is not None else build_evidence_for_sample(sample, issues)

    return AnswerAnalysisRecord(
        interview_id=sample.interview_id,
        participant_id=sample.participant_id,
        question_id=sample.question_id,
        recording_id=sample.recording_id,
        question_text=sample.question_text,
        transcript=sample.transcript,
        question_start=sample.question_start,
        question_end=sample.question_end,
        answer_start=sample.answer_start,
        answer_end=sample.answer_end,
        response_latency=sample.response_latency,
        answer_duration=sample.answer_duration,
        transcript_segments=segments,
        has_word_timestamps=has_words,
        has_segment_timestamps=has_segs,
        audio_timing_features=audio_timing,
        linguistic_features=linguistic,
        recording_quality_features=quality_feats,
        provenance_features=provenance,
        evidence_signals=[s.to_dict() for s in signals],
        sample_row=sample.to_row(),
    )


def build_analysis_document(
    samples: list[InterviewSample],
    issues: list[QualityIssue],
    detection: DetectionInference,
    *,
    provenance: AnalysisProvenance,
    processing_error: str | None = None,
    errors: list[str] | None = None,
) -> OfflineAnalysisDocument:
    analysis_id = provenance.analysis_id or new_analysis_id()
    provenance.analysis_id = analysis_id
    provenance.schema_version = ANALYSIS_SCHEMA_VERSION

    evidence_by_sample: list[list[EvidenceSignal]] = []
    answers: list[AnswerAnalysisRecord] = []
    for sample in samples:
        sample_issues = [i for i in issues if i.key.startswith("/".join(p for p in sample.key if p))]
        evidence = build_evidence_for_sample(sample, sample_issues or issues)
        evidence_by_sample.append(evidence)
        answers.append(answer_record_from_sample(sample, issues=sample_issues or issues, evidence=evidence))

    if processing_error:
        state: ProcessingState = "failed"
    elif any(i.severity == "error" for i in issues) or any(i.severity == "warning" for i in issues):
        state = "completed_with_warnings" if samples else "failed"
        if samples and not any(i.severity == "error" for i in issues):
            state = "completed_with_warnings"
        elif samples:
            state = "completed_with_warnings"
        else:
            state = "failed"
    elif samples:
        state = "completed"
    else:
        state = "failed"

    # Prefer completed_with_warnings when there are warnings but processing succeeded.
    if samples and not processing_error:
        if any(i.severity in {"error", "warning"} for i in issues):
            state = "completed_with_warnings"
        else:
            state = "completed"

    return OfflineAnalysisDocument(
        schema_version=ANALYSIS_SCHEMA_VERSION,
        analysis_id=analysis_id,
        processing_state=state,
        source=provenance.source,
        is_synthetic=provenance.is_synthetic,
        provenance=provenance,
        answers=answers,
        quality_issues=[asdict(i) for i in issues],
        detection=detection.to_dict(),
        errors=list(errors or []),
        processing_error=processing_error,
    )


def document_from_dict(data: dict[str, Any]) -> OfflineAnalysisDocument:
    """Rehydrate a document dict (for tests / transport mocks). Provenance is shallow."""
    prov_raw = dict(data.get("provenance") or {})
    provenance = AnalysisProvenance(
        schema_version=str(prov_raw.get("schema_version") or data.get("schema_version") or ANALYSIS_SCHEMA_VERSION),
        analysis_id=str(prov_raw.get("analysis_id") or data.get("analysis_id") or ""),
        source=prov_raw.get("source") or data.get("source") or "offline_processing",  # type: ignore[arg-type]
        is_synthetic=bool(prov_raw.get("is_synthetic", data.get("is_synthetic", False))),
        transcript_mode=prov_raw.get("transcript_mode") or "none",  # type: ignore[arg-type]
        stt_requested=prov_raw.get("stt_requested"),
        stt_options=dict(prov_raw.get("stt_options") or {}),
        video_path=prov_raw.get("video_path"),
        metadata_ref=prov_raw.get("metadata_ref"),
        transcript_path=prov_raw.get("transcript_path"),
        pipeline=str(prov_raw.get("pipeline") or "interview_integrity.services.analyze_offline_recording"),
    )
    answers: list[AnswerAnalysisRecord] = []
    for raw in data.get("answers") or []:
        segs = [
            TranscriptSegmentRecord(
                id=s["id"],
                text=s.get("text") or "",
                start_seconds=s.get("start_seconds"),
                end_seconds=s.get("end_seconds"),
                speaker=s.get("speaker"),
                words=list(s.get("words") or []),
            )
            for s in (raw.get("transcript_segments") or [])
        ]
        answers.append(
            AnswerAnalysisRecord(
                interview_id=raw["interview_id"],
                participant_id=raw["participant_id"],
                question_id=raw["question_id"],
                recording_id=raw["recording_id"],
                question_text=raw.get("question_text"),
                transcript=raw.get("transcript"),
                question_start=raw.get("question_start"),
                question_end=raw.get("question_end"),
                answer_start=raw.get("answer_start"),
                answer_end=raw.get("answer_end"),
                response_latency=raw.get("response_latency"),
                answer_duration=raw.get("answer_duration"),
                transcript_segments=segs,
                has_word_timestamps=bool(raw.get("has_word_timestamps")),
                has_segment_timestamps=bool(raw.get("has_segment_timestamps")),
                audio_timing_features=dict(raw.get("audio_timing_features") or {}),
                linguistic_features=dict(raw.get("linguistic_features") or {}),
                recording_quality_features=dict(raw.get("recording_quality_features") or {}),
                provenance_features=dict(raw.get("provenance_features") or {}),
                evidence_signals=list(raw.get("evidence_signals") or []),
                sample_row=dict(raw.get("sample_row") or {}),
            )
        )
    return OfflineAnalysisDocument(
        schema_version=str(data.get("schema_version") or ANALYSIS_SCHEMA_VERSION),
        analysis_id=str(data.get("analysis_id") or provenance.analysis_id),
        processing_state=data.get("processing_state") or "failed",  # type: ignore[arg-type]
        source=data.get("source") or provenance.source,  # type: ignore[arg-type]
        is_synthetic=bool(data.get("is_synthetic", provenance.is_synthetic)),
        provenance=provenance,
        answers=answers,
        quality_issues=list(data.get("quality_issues") or []),
        detection=dict(data.get("detection") or {}),
        errors=list(data.get("errors") or []),
        processing_error=data.get("processing_error"),
    )
