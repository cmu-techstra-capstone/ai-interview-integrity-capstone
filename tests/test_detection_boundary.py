"""Aditi detection boundary: unavailable by default; mocks only in tests."""

from __future__ import annotations

import pytest

from interview_integrity.datasets.schema import AssistanceLabel, InterviewSample, SourceDataset
from interview_integrity.detection.boundary import (
    ADITI_CONFIRMATION_NEEDED,
    ConfidenceStatus,
    DetectionInference,
    DetectionStatus,
    ModelUnavailableDetector,
    run_detection,
)
from interview_integrity.evidence import EvidenceSignal, QualityStatus
from interview_integrity.features.registry import Modality


def _sample(**kwargs) -> InterviewSample:
    base = dict(
        interview_id="INT001",
        participant_id="P001",
        question_id="Q01",
        source_dataset=SourceDataset.STAGED,
        assistance_label=AssistanceLabel.HUMAN_UNASSISTED,
        question_text="Why test?",
        transcript="Um, testing catches bugs.",
        answer_start=0.5,
        answer_end=1.5,
        features={"filler_word_count": 1, "speech_rate_wpm": 120.0},
    )
    base.update(kwargs)
    return InterviewSample(**base)


def test_default_model_unavailable():
    sample = _sample()
    result = run_detection([sample], { "INT001/Q01": [] })
    assert result.status is DetectionStatus.MODEL_UNAVAILABLE
    assert result.raw_score is None
    assert result.confidence_status is ConfidenceStatus.UNAVAILABLE_NOT_CALIBRATED
    assert result.confidence_value is None


def test_empty_samples_default_is_model_unavailable():
    result = run_detection([], {})
    assert result.status is DetectionStatus.MODEL_UNAVAILABLE


def test_empty_samples_with_mock_model_is_insufficient_evidence():
    class _Mock:
        name = "mock"
        version = "0"

        def infer(self, sample, evidence):
            raise AssertionError("should not be called with empty samples")

    result = run_detection([], {}, model=_Mock())
    assert result.status is DetectionStatus.INSUFFICIENT_EVIDENCE


def test_mock_inference_available_in_tests_only():
    class _MockOk:
        name = "mock-aditi"
        version = "test-0"

        def infer(self, sample, evidence):
            return DetectionInference(
                status=DetectionStatus.INFERENCE_AVAILABLE,
                message="Mock inference for tests only.",
                confidence_status=ConfidenceStatus.UNAVAILABLE_NOT_CALIBRATED,
                model_name=self.name,
                model_version=self.version,
                review_label="Mock review label — not a cheating verdict.",
                review_status="Requires review",
                raw_score=0.42,
                related_question_id=sample.question_id,
                calibrated=None,
            ).validate()

    result = run_detection([_sample()], {}, model=_MockOk())
    assert result.status is DetectionStatus.INFERENCE_AVAILABLE
    assert result.raw_score == 0.42
    assert result.confidence_value is None


def test_mock_insufficient_evidence():
    class _MockInsufficient:
        name = "mock"
        version = "0"

        def infer(self, sample, evidence):
            return DetectionInference(
                status=DetectionStatus.INSUFFICIENT_EVIDENCE,
                message="Mock: not enough evidence.",
                confidence_status=ConfidenceStatus.UNAVAILABLE_NOT_PROVIDED,
                related_question_id=sample.question_id,
            ).validate()

    result = run_detection([_sample()], {}, model=_MockInsufficient())
    assert result.status is DetectionStatus.INSUFFICIENT_EVIDENCE


def test_mock_model_error_is_caught():
    class _Boom:
        name = "boom"
        version = "0"

        def infer(self, sample, evidence):
            raise RuntimeError("simulated model failure")

    result = run_detection([_sample()], {}, model=_Boom())
    assert result.status is DetectionStatus.MODEL_ERROR
    assert result.error and "RuntimeError" in result.error


def test_unavailable_rejects_raw_score():
    with pytest.raises(ValueError):
        DetectionInference(
            status=DetectionStatus.MODEL_UNAVAILABLE,
            message="x",
            raw_score=0.9,
        ).validate()


def test_provided_confidence_requires_calibration_flag():
    with pytest.raises(ValueError):
        DetectionInference(
            status=DetectionStatus.INFERENCE_AVAILABLE,
            message="x",
            review_label="y",
            confidence_status=ConfidenceStatus.PROVIDED,
            confidence_value=0.5,
            calibrated=None,
        ).validate()


def test_aditi_confirmation_list_is_nonempty():
    assert len(ADITI_CONFIRMATION_NEEDED) >= 5


def test_model_unavailable_detector_ignores_evidence_content():
    sig = EvidenceSignal(
        signal_name="filler_word_count",
        modality=Modality.TRANSCRIPT,
        value=3,
        quality_status=QualityStatus.OK,
        explanation="count",
        sample_key="INT001/Q01",
        source_features=("filler_word_count",),
    ).validate()
    out = ModelUnavailableDetector().infer(_sample(), [sig])
    assert out.status is DetectionStatus.MODEL_UNAVAILABLE
    assert out.detection_evidence == ()
