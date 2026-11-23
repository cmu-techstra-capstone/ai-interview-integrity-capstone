"""Evidence contract: the shape future audio/transcript/visual signals must take.

Defines *what* a reviewable signal looks like. It does not decide which signals indicate AI
assistance, how to weigh them, or any score; those decisions are not approved yet.
``confidence`` stays ``None`` until a scoring method is approved.

A signal is always paired with the quality of the modality it came from, so poor
recordings degrade trust in signals instead of becoming signals themselves.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any

from .datasets.quality import QualityIssue, check_sample
from .datasets.schema import InterviewSample
from .features.registry import FeatureKind, Modality, spec_for


class EvidenceError(ValueError):
    pass


class QualityStatus(str, enum.Enum):
    OK = "ok"
    WARNING = "warning"
    UNUSABLE = "unusable"
    UNKNOWN = "unknown"


# Which quality issues affect which modality's signals.
ISSUE_MODALITIES: dict[str, set[Modality]] = {
    "SILENT_AUDIO": {Modality.AUDIO}, "NO_SPEECH_DETECTED": {Modality.AUDIO},
    "NOISY_RECORDING": {Modality.AUDIO}, "CLIPPED_AUDIO": {Modality.AUDIO},
    "MISSING_TIMING": {Modality.AUDIO}, "INVALID_DURATION": {Modality.AUDIO, Modality.TRANSCRIPT},
    "IMPOSSIBLE_TIMING": {Modality.AUDIO, Modality.TRANSCRIPT}, "VERY_SHORT_ANSWER": {Modality.AUDIO},
    "EXTREME_SPEECH_RATE": {Modality.AUDIO}, "EXTREME_ARTICULATION_RATE": {Modality.AUDIO},
    "NEGATIVE_LATENCY": {Modality.AUDIO}, "MISSING_TRANSCRIPT": {Modality.TRANSCRIPT},
}


@dataclass(frozen=True)
class TranscriptSpan:
    text: str
    start: float | None = None
    end: float | None = None


@dataclass(frozen=True)
class EvidenceSignal:
    signal_name: str
    modality: Modality
    value: float | int | str | bool | None
    quality_status: QualityStatus
    explanation: str
    sample_key: str
    confidence: float | None = None  # reserved; None until a scoring method is approved
    supporting_timestamps: tuple[tuple[float, float], ...] = ()
    supporting_transcript_span: TranscriptSpan | None = None
    source_features: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> "EvidenceSignal":
        if not self.signal_name or not self.explanation.strip():
            raise EvidenceError("signal_name and explanation are required")
        if not isinstance(self.modality, Modality) or not isinstance(self.quality_status, QualityStatus):
            raise EvidenceError("modality and quality_status must be enum members")
        if self.value is not None and not isinstance(self.value, (str, int, float, bool)):
            raise EvidenceError(f"{self.signal_name}: value must be a scalar")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise EvidenceError(f"{self.signal_name}: confidence must be in [0, 1]")
        for s, e in self.supporting_timestamps:
            if s < 0 or e < s:
                raise EvidenceError(f"{self.signal_name}: invalid timestamp span ({s}, {e})")
        for name in self.source_features:
            spec = spec_for(name)
            if spec is not None and spec.kind is FeatureKind.QUALITY:
                raise EvidenceError(f"{self.signal_name}: quality feature {name!r} cannot be used as evidence")
        return self

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["modality"], d["quality_status"] = self.modality.value, self.quality_status.value
        return d


def modality_quality(sample: InterviewSample, issues: list[QualityIssue] | None = None) -> dict[Modality, QualityStatus]:
    """Quality status per modality for one sample, derived from its quality issues."""
    issues = check_sample(sample) if issues is None else issues
    status = {m: QualityStatus.OK for m in (Modality.AUDIO, Modality.TRANSCRIPT)}
    status[Modality.VISUAL] = QualityStatus.UNKNOWN  # no visual pipeline yet
    rank = {QualityStatus.OK: 0, QualityStatus.WARNING: 1, QualityStatus.UNUSABLE: 2}
    for issue in issues:
        new = QualityStatus.UNUSABLE if issue.severity == "error" else QualityStatus.WARNING
        for m in ISSUE_MODALITIES.get(issue.code, set()):
            if rank[new] > rank[status[m]]:
                status[m] = new
    return status


def describe_feature(sample: InterviewSample, feature: str, quality: dict[Modality, QualityStatus] | None = None) -> EvidenceSignal:
    """Wrap one behavioral feature as a neutral, descriptive signal (no interpretation, no confidence).

    Reference implementation of the contract for teammates; it states what was measured,
    not what it means.
    """
    spec = spec_for(feature)
    if spec is None or spec.kind is not FeatureKind.BEHAVIORAL:
        raise EvidenceError(f"{feature!r} is not a registered behavioral feature")
    quality = quality or modality_quality(sample)
    value = sample.features.get(feature)
    window = ((sample.answer_start, sample.answer_end),) if sample.answer_start is not None and sample.answer_end is not None else ()
    span = TranscriptSpan(sample.transcript, sample.answer_start, sample.answer_end) \
        if spec.modality is Modality.TRANSCRIPT and sample.transcript else None
    status = quality.get(spec.modality, QualityStatus.UNKNOWN) if value is not None else QualityStatus.UNKNOWN
    unit = f" {spec.unit}" if spec.unit and value is not None else ""
    explanation = f"{spec.description}: {value if value is not None else 'not measurable'}{unit}."
    return EvidenceSignal(
        signal_name=feature, modality=spec.modality, value=value, quality_status=status,
        explanation=explanation, sample_key="/".join(p for p in sample.key if p),
        supporting_timestamps=window, supporting_transcript_span=span, source_features=(feature,),
    ).validate()
