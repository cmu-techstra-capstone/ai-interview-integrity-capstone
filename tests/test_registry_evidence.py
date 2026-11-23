"""Feature registry (behavioral vs quality vs provenance), plug-in namespaces and the evidence contract."""

import pytest

from interview_integrity.datasets.schema import InterviewSample
from interview_integrity.evidence import (
    EvidenceError,
    EvidenceSignal,
    QualityStatus,
    TranscriptSpan,
    describe_feature,
    modality_quality,
)
from interview_integrity.features.base import FeatureExtractorError
from interview_integrity.features.registry import FEATURES, FeatureKind, Modality, spec_for, split_by_kind
from interview_integrity.pipeline import PipelineConfig, process_video
from interview_integrity.transcription import SidecarTranscriber

from .conftest import requires_ffmpeg


@requires_ffmpeg
def test_every_core_feature_is_registered(sample_video, metadata_dict, transcript_path, tmp_path):
    [s] = process_video(sample_video, metadata_dict, transcriber=SidecarTranscriber(transcript_path),
                        config=PipelineConfig(interim_dir=tmp_path))
    unregistered = [k for k in s.features if spec_for(k) is None]
    assert unregistered == [], f"register new features in features/registry.py: {unregistered}"


def test_quality_features_are_never_behavioral():
    for name, spec in FEATURES.items():
        if name.startswith("audio_"):
            assert spec.kind is FeatureKind.QUALITY and spec.modality is Modality.RECORDING


def test_plugin_prefix_resolution_and_split():
    assert spec_for("visual_blink_rate").modality is Modality.VISUAL
    assert spec_for("quality_face_visible").kind is FeatureKind.QUALITY
    groups = split_by_kind({"pause_count": 1, "audio_snr_db": 20.0, "timing_source": "x", "mystery": 1})
    assert set(groups[FeatureKind.BEHAVIORAL]) == {"pause_count"}
    assert set(groups[FeatureKind.QUALITY]) == {"audio_snr_db"}
    assert set(groups[None]) == {"mystery"}


class _Plugin:
    def __init__(self, name, prefix, out):
        self.name, self.prefix, self._out = name, prefix, out

    def extract(self, ctx):
        return self._out


@requires_ffmpeg
@pytest.mark.parametrize("plugins,match", [
    ([_Plugin("a", "speech_", {"speech_x": 1})], "must start with one of"),
    ([_Plugin("a", "visual_", {"visual_x": 1}), _Plugin("b", "visual_", {"visual_x": 2})], "already used"),
    ([_Plugin("a", "visual_", {"visual_x": [1, 2]})], "scalars"),
])
def test_plugin_namespace_protection(sample_video, metadata_dict, tmp_path, plugins, match):
    with pytest.raises(FeatureExtractorError, match=match):
        process_video(sample_video, metadata_dict, config=PipelineConfig(interim_dir=tmp_path, extractors=plugins))


@requires_ffmpeg
def test_two_plugins_with_distinct_namespaces_coexist(sample_video, metadata_dict, tmp_path):
    plugins = [_Plugin("gaze", "visual_gaze_", {"visual_gaze_x": 1.0}),
               _Plugin("face", "quality_face_", {"quality_face_visible": True})]
    [s] = process_video(sample_video, metadata_dict, config=PipelineConfig(interim_dir=tmp_path, extractors=plugins))
    assert s.features["visual_gaze_x"] == 1.0 and s.features["quality_face_visible"] is True


# ---------------------------------------------------------------- evidence contract

def _sample(**features):
    return InterviewSample(
        interview_id="I1", participant_id="P1", question_id="Q1", source_dataset="staged",
        assistance_label="HUMAN_UNASSISTED", transcript="Um, I think so.", answer_start=2.0, answer_end=10.0,
        answer_duration=8.0, features={"speech_duration": 6.0, "speech_rate_wpm": 140.0, **features},
    ).validate()


def test_signal_validation():
    base = dict(signal_name="pause_count", modality=Modality.AUDIO, value=3, quality_status=QualityStatus.OK,
                explanation="Pauses ≥ 0.3 s: 3", sample_key="I1/Q1")
    EvidenceSignal(**base).validate()
    for bad in (dict(confidence=1.5), dict(explanation=" "), dict(supporting_timestamps=((5.0, 2.0),)),
                dict(value=[1]), dict(source_features=("audio_snr_db",))):
        with pytest.raises(EvidenceError):
            EvidenceSignal(**{**base, **bad}).validate()


def test_quality_degrades_signals_instead_of_becoming_evidence():
    noisy = _sample(audio_is_noisy=True, audio_snr_db=8.0, long_pause_count=2)
    q = modality_quality(noisy)
    assert q[Modality.AUDIO] is QualityStatus.WARNING and q[Modality.TRANSCRIPT] is QualityStatus.OK
    sig = describe_feature(noisy, "long_pause_count", q)
    assert sig.quality_status is QualityStatus.WARNING and sig.confidence is None
    assert sig.supporting_timestamps == ((2.0, 10.0),)
    with pytest.raises(EvidenceError, match="not a registered behavioral"):
        describe_feature(noisy, "audio_is_noisy")


def test_silent_audio_makes_audio_signals_unusable_and_transcript_signal_has_span():
    s = _sample(audio_is_silent=True, filler_word_count=1)
    q = modality_quality(s)
    assert q[Modality.AUDIO] is QualityStatus.UNUSABLE and q[Modality.VISUAL] is QualityStatus.UNKNOWN
    sig = describe_feature(s, "filler_word_count", q)
    assert sig.supporting_transcript_span == TranscriptSpan("Um, I think so.", 2.0, 10.0)
    assert sig.to_dict()["modality"] == "transcript"


def test_missing_value_is_explicit():
    sig = describe_feature(_sample(), "speech_rate_cv")
    assert sig.value is None and sig.quality_status is QualityStatus.UNKNOWN
    assert "not measurable" in sig.explanation
