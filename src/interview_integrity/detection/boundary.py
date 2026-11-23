"""Clean integration boundary for Aditi's future AI-assistance detection model.

Outcomes are deliberately distinguished. No fusion formula, risk thresholds, output
labels, or confidence calibration are chosen here — those require Aditi's confirmation.

Production default: :class:`ModelUnavailableDetector` (honest ``model_unavailable``).
Mock implementations belong in tests only.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from ..datasets.schema import InterviewSample
from ..evidence import EvidenceSignal


class DetectionStatus(str, enum.Enum):
    MODEL_UNAVAILABLE = "model_unavailable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    MODEL_ERROR = "model_error"
    INFERENCE_AVAILABLE = "inference_available"


class ConfidenceStatus(str, enum.Enum):
    UNAVAILABLE_NOT_CALIBRATED = "unavailable_not_calibrated"
    UNAVAILABLE_NOT_PROVIDED = "unavailable_not_provided"
    PROVIDED = "provided"


@dataclass(frozen=True)
class DetectionInference:
    """Result of one detection-boundary call (never a fabricated cheating score)."""

    status: DetectionStatus
    message: str
    confidence_status: ConfidenceStatus = ConfidenceStatus.UNAVAILABLE_NOT_CALIBRATED
    confidence_value: float | None = None
    calibrated: bool | None = None
    model_name: str | None = None
    model_version: str | None = None
    # Populated only when a real compatible model returns them — never invented here.
    review_label: str | None = None
    review_status: str | None = None
    raw_score: float | None = None
    detection_evidence: tuple[dict[str, Any], ...] = ()
    related_question_id: str | None = None
    warnings: tuple[str, ...] = ()
    # Separates processing/model failure from "model simply not plugged in".
    error: str | None = None

    def validate(self) -> "DetectionInference":
        if self.status is DetectionStatus.INFERENCE_AVAILABLE:
            if self.raw_score is None and self.review_status is None and self.review_label is None:
                raise ValueError("inference_available requires at least one model-provided field")
        if self.confidence_status is ConfidenceStatus.PROVIDED:
            if self.confidence_value is None or not 0.0 <= self.confidence_value <= 1.0:
                raise ValueError("provided confidence requires a value in [0, 1]")
            if self.calibrated is None:
                raise ValueError("provided confidence must declare calibrated=True|False")
        else:
            if self.confidence_value is not None:
                raise ValueError("confidence_value must be None unless confidence is provided")
        if self.status is DetectionStatus.MODEL_UNAVAILABLE and self.raw_score is not None:
            raise ValueError("model_unavailable must not carry a raw_score")
        return self

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["confidence_status"] = self.confidence_status.value
        d["detection_evidence"] = list(self.detection_evidence)
        d["warnings"] = list(self.warnings)
        return d


class DetectionModel(Protocol):
    """Adapter protocol for Aditi's model once input/output schemas are confirmed."""

    name: str
    version: str

    def infer(
        self,
        sample: InterviewSample,
        evidence: list[EvidenceSignal],
    ) -> DetectionInference:
        """Run detection for one answer.

        Implementations must not invent calibrated confidence or cheating probabilities.
        They may return ``insufficient_evidence``, ``model_error``, or ``inference_available``.
        """


@dataclass
class ModelUnavailableDetector:
    """Production default until Aditi's compatible adapter is approved and wired."""

    name: str = "aditi-detection"
    version: str = "unavailable"
    note: str = (
        "Aditi's detection model is not integrated yet. Descriptive audio/transcript "
        "features are not model inference."
    )

    def infer(
        self,
        sample: InterviewSample,
        evidence: list[EvidenceSignal],
    ) -> DetectionInference:
        return DetectionInference(
            status=DetectionStatus.MODEL_UNAVAILABLE,
            message=self.note,
            confidence_status=ConfidenceStatus.UNAVAILABLE_NOT_CALIBRATED,
            model_name=self.name,
            model_version=self.version,
            related_question_id=sample.question_id,
            warnings=(
                "No AI-assistance detection model is available in this build.",
                "EvidenceSignal feature descriptions are measurements, not proof of AI assistance.",
            ),
        ).validate()


def run_detection(
    samples: list[InterviewSample],
    evidence_by_key: dict[str, list[EvidenceSignal]],
    *,
    model: DetectionModel | None = None,
) -> DetectionInference:
    """Run the detection boundary for the first sample (answer-level MVP).

    Default model is :class:`ModelUnavailableDetector`. Passing ``model`` is for tests
    or a future approved adapter only.
    """
    detector: DetectionModel = model or ModelUnavailableDetector()
    if not samples:
        # No answers: with the production default this is still "model unavailable"
        # (processing may have failed separately). A plugged-in model may report
        # insufficient evidence instead.
        if model is None:
            return DetectionInference(
                status=DetectionStatus.MODEL_UNAVAILABLE,
                message=(
                    "Aditi's detection model is not integrated yet, and no answer "
                    "samples are available for detection."
                ),
                confidence_status=ConfidenceStatus.UNAVAILABLE_NOT_CALIBRATED,
                model_name=getattr(detector, "name", None),
                model_version=getattr(detector, "version", None),
                warnings=("No answer samples available for detection.",),
            ).validate()
        return DetectionInference(
            status=DetectionStatus.INSUFFICIENT_EVIDENCE,
            message="No answer samples available for detection.",
            confidence_status=ConfidenceStatus.UNAVAILABLE_NOT_PROVIDED,
            model_name=getattr(detector, "name", None),
            model_version=getattr(detector, "version", None),
        ).validate()
    sample = samples[0]
    key = "/".join(p for p in sample.key if p)
    evidence = evidence_by_key.get(key, [])
    try:
        return detector.infer(sample, evidence).validate()
    except Exception as exc:  # noqa: BLE001 — boundary must surface model errors distinctly
        return DetectionInference(
            status=DetectionStatus.MODEL_ERROR,
            message=f"Detection model raised {type(exc).__name__}.",
            confidence_status=ConfidenceStatus.UNAVAILABLE_NOT_PROVIDED,
            model_name=getattr(detector, "name", None),
            model_version=getattr(detector, "version", None),
            related_question_id=sample.question_id,
            error=f"{type(exc).__name__}: {exc}",
        ).validate()


# Open questions that must be confirmed with Aditi before a real adapter ships.
ADITI_CONFIRMATION_NEEDED: tuple[str, ...] = (
    "Exact model input schema (features, transcript window, audio refs, metadata).",
    "Exact model output schema (labels, raw scores, optional confidence).",
    "Whether confidence is calibrated; if not, confidence must stay unavailable.",
    "Review-oriented label vocabulary (must not claim 'cheating confirmed').",
    "Minimum evidence requirements for insufficient_evidence vs runnable inference.",
    "Feature transforms / normalizations required before inference.",
    "Fusion or scoring formula across modalities (if any) — not decided here.",
    "Risk thresholds for human-review banners (if any) — not decided here.",
)
