"""Deterministic end-to-end offline analysis → analysis.v1 contract (no model downloads)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_integrity.analysis_contract import (
    ANALYSIS_SCHEMA_VERSION,
    document_from_dict,
)
from interview_integrity.cli import main
from interview_integrity.detection.boundary import DetectionStatus
from interview_integrity.pipeline import PipelineConfig
from interview_integrity.services import analyze_offline_recording, resolve_transcriber
from interview_integrity.transcription.adapters.faster_whisper import FasterWhisperTranscriber
from interview_integrity.transcription.base import TranscriptionError
from interview_integrity.transcription.registry import FASTER_WHISPER_BASELINE_NAME

from .conftest import requires_ffmpeg

FIXTURES = Path(__file__).parent / "fixtures"
CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


@pytest.fixture
def out_dir(tmp_path):
    d = tmp_path / "processed"
    d.mkdir()
    return d


@pytest.fixture
def interim(tmp_path):
    d = tmp_path / "interim"
    d.mkdir()
    return d


def _meta_single() -> dict:
    return json.loads((FIXTURES / "sample_metadata.json").read_text())


def _meta_multi() -> dict:
    return {
        "interview_id": "INT-MULTI",
        "participant_id": "P001",
        "recording_id": "INT-MULTI",
        "source_dataset": "staged",
        "questions": [
            {
                "question_id": "Q01",
                "question_text": "Why does software testing matter?",
                "assistance_label": "HUMAN_UNASSISTED",
                "question_start": 0.0,
                "question_end": 0.4,
                "answer_start": 0.5,
                "answer_end": 1.5,
            },
            {
                "question_id": "Q02",
                "question_text": "How do you debug production issues?",
                "assistance_label": "HUMAN_UNASSISTED",
                "question_start": 1.6,
                "question_end": 2.4,
                "answer_start": 2.5,
                "answer_end": 3.5,
            },
        ],
    }


@requires_ffmpeg
def test_e2e_sidecar_path_produces_contract(sample_video, transcript_path, out_dir, interim):
    result = analyze_offline_recording(
        sample_video,
        _meta_single(),
        transcript=transcript_path,
        out_dir=out_dir,
        config=PipelineConfig(interim_dir=interim),
    )
    assert result.processing_error is None
    assert result.detection is not None
    assert result.detection.status is DetectionStatus.MODEL_UNAVAILABLE
    assert result.analysis_document is not None
    doc = result.to_analysis_dict()
    assert doc["schema_version"] == ANALYSIS_SCHEMA_VERSION
    assert doc["source"] == "offline_processing"
    assert doc["is_synthetic"] is False
    assert doc["processing_state"] in {"completed", "completed_with_warnings"}
    assert doc["provenance"]["transcript_mode"] == "sidecar"
    assert len(doc["answers"]) == 1
    answer = doc["answers"][0]
    assert answer["question_id"] == "Q01"
    assert answer["transcript"]
    assert answer["has_word_timestamps"] is True
    assert answer["transcript_segments"]
    assert answer["linguistic_features"].get("filler_word_count") is not None
    assert "audio_is_silent" in answer["recording_quality_features"] or answer["recording_quality_features"]
    assert answer["evidence_signals"]
    # Evidence is descriptive — not a detection verdict.
    assert all("signal_name" in e for e in answer["evidence_signals"])
    assert doc["detection"]["status"] == "model_unavailable"
    assert doc["detection"]["raw_score"] is None
    assert doc["detection"]["confidence_value"] is None
    assert (out_dir / "analysis.json").is_file()
    assert (out_dir / "samples.jsonl").is_file()


@requires_ffmpeg
def test_e2e_no_stt_vad_fallback(sample_video, out_dir, interim):
    result = analyze_offline_recording(
        sample_video,
        _meta_single(),
        out_dir=out_dir,
        config=PipelineConfig(interim_dir=interim),
    )
    doc = result.to_analysis_dict()
    assert doc["provenance"]["transcript_mode"] == "none"
    assert doc["detection"]["status"] == "model_unavailable"
    answer = doc["answers"][0]
    assert answer["linguistic_features"].get("word_count") is None or answer["transcript"] in (None, "")
    assert answer["provenance_features"].get("timing_source") == "energy_vad"
    # Missing transcript should surface as a quality warning, not as fabricated detection.
    codes = {i["code"] for i in doc["quality_issues"]}
    assert "MISSING_TRANSCRIPT" in codes
    assert doc["is_synthetic"] is False


@requires_ffmpeg
def test_e2e_multi_question_windows(sample_video, transcript_path, out_dir, interim):
    result = analyze_offline_recording(
        sample_video,
        _meta_multi(),
        transcript=transcript_path,
        out_dir=out_dir,
        config=PipelineConfig(interim_dir=interim),
    )
    doc = result.to_analysis_dict()
    assert [a["question_id"] for a in doc["answers"]] == ["Q01", "Q02"]
    for a in doc["answers"]:
        assert a["answer_start"] is not None and a["answer_end"] is not None
        assert a["answer_end"] > a["answer_start"]
        # Windowed transcript should not be empty for tone-aligned segments.
        assert a["transcript"]


@requires_ffmpeg
def test_sidecar_precedence_over_stt(sample_video, transcript_path, out_dir, interim, monkeypatch):
    calls = {"n": 0}

    def _boom(self, audio_path):
        calls["n"] += 1
        raise AssertionError("STT must not run when sidecar is provided")

    monkeypatch.setattr(FasterWhisperTranscriber, "transcribe", _boom)
    result = analyze_offline_recording(
        sample_video,
        _meta_single(),
        transcript=transcript_path,
        stt=FASTER_WHISPER_BASELINE_NAME,
        out_dir=out_dir,
        config=PipelineConfig(interim_dir=interim),
    )
    assert calls["n"] == 0
    assert result.to_analysis_dict()["provenance"]["transcript_mode"] == "sidecar"
    # resolve_transcriber also prefers sidecar
    tr = resolve_transcriber(transcript=transcript_path, stt=FASTER_WHISPER_BASELINE_NAME)
    assert tr is not None
    assert getattr(tr, "name", None) == "sidecar"


@requires_ffmpeg
def test_stt_selection_failure_is_processing_error_not_detection(sample_video, out_dir, interim):
    from interview_integrity.transcription.base import Transcriber

    class _FailingStt(Transcriber):
        name = FASTER_WHISPER_BASELINE_NAME

        def transcribe(self, audio_path):
            raise TranscriptionError("simulated STT failure (no weights)")

    result = analyze_offline_recording(
        sample_video,
        _meta_single(),
        transcriber=_FailingStt(),
        stt=FASTER_WHISPER_BASELINE_NAME,
        out_dir=out_dir,
        config=PipelineConfig(interim_dir=interim),
        write_outputs=False,
    )
    assert result.processing_error is not None
    assert "TranscriptionError" in result.processing_error or "simulated STT" in result.processing_error
    doc = result.to_analysis_dict()
    assert doc["processing_state"] == "failed"
    assert doc["processing_error"]
    # Detection still reports model unavailable (separate from processing failure).
    assert doc["detection"]["status"] == "model_unavailable"
    assert doc["answers"] == []
    assert doc["provenance"]["stt_requested"] == FASTER_WHISPER_BASELINE_NAME


@requires_ffmpeg
def test_silent_low_quality_flags(silent_audio_video, out_dir, interim):
    result = analyze_offline_recording(
        silent_audio_video,
        _meta_single(),
        out_dir=out_dir,
        config=PipelineConfig(interim_dir=interim),
    )
    doc = result.to_analysis_dict()
    codes = {i["code"] for i in doc["quality_issues"]}
    assert "SILENT_AUDIO" in codes or "NO_SPEECH_DETECTED" in codes
    answer = doc["answers"][0]
    qf = answer["recording_quality_features"]
    assert qf.get("audio_is_silent") in (True, 1, "true", None) or "SILENT_AUDIO" in codes
    assert doc["detection"]["status"] == "model_unavailable"


@requires_ffmpeg
def test_valid_and_missing_timestamps(sample_video, out_dir, interim, tmp_path):
    # Timestamped sidecar
    ts = FIXTURES / "sample_transcript.json"
    with_ts = analyze_offline_recording(
        sample_video, _meta_single(), transcript=ts, out_dir=out_dir / "a",
        config=PipelineConfig(interim_dir=interim / "a"),
    ).to_analysis_dict()
    assert with_ts["answers"][0]["has_word_timestamps"] is True

    # Plain-text sidecar — no timestamps
    plain = tmp_path / "plain.transcript.txt"
    plain.write_text("I think testing matters a lot.")
    no_ts = analyze_offline_recording(
        sample_video, _meta_single(), transcript=plain, out_dir=out_dir / "b",
        config=PipelineConfig(interim_dir=interim / "b"),
    ).to_analysis_dict()
    assert no_ts["answers"][0]["has_word_timestamps"] is False
    assert no_ts["answers"][0]["transcript"]


@requires_ffmpeg
def test_schema_roundtrip_and_golden_contract_keys(sample_video, transcript_path, tmp_path):
    interim = tmp_path / "i"
    interim.mkdir()
    out = tmp_path / "o"
    out.mkdir()
    doc = analyze_offline_recording(
        sample_video,
        _meta_single(),
        transcript=transcript_path,
        out_dir=out,
        config=PipelineConfig(interim_dir=interim),
        analysis_id="anl_testfixture01",
    ).to_analysis_dict()
    restored = document_from_dict(doc).to_dict()
    assert restored["schema_version"] == doc["schema_version"]
    assert restored["analysis_id"] == "anl_testfixture01"
    required = {
        "schema_version",
        "analysis_id",
        "processing_state",
        "source",
        "is_synthetic",
        "provenance",
        "answers",
        "quality_issues",
        "detection",
        "errors",
        "processing_error",
    }
    assert required <= set(doc)
    answer_keys = {
        "interview_id",
        "question_id",
        "question_text",
        "transcript",
        "transcript_segments",
        "audio_timing_features",
        "linguistic_features",
        "recording_quality_features",
        "evidence_signals",
        "sample_row",
    }
    assert answer_keys <= set(doc["answers"][0])
    # Persist golden for TypeScript contract-compat tests.
    CONTRACTS.mkdir(exist_ok=True)
    golden = CONTRACTS / "analysis.v1.example.json"
    # Stable-ish example: rewrite analysis_id for the checked-in golden shape.
    example = dict(doc)
    example["analysis_id"] = "anl_example0001"
    example["provenance"] = {**example["provenance"], "analysis_id": "anl_example0001", "video_path": "<fixture>"}
    golden.write_text(json.dumps(example, indent=2, sort_keys=True) + "\n")
    assert golden.is_file()


@requires_ffmpeg
def test_cli_analyze_offline(sample_video, transcript_path, tmp_path, capsys):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(_meta_single()))
    out = tmp_path / "out"
    code = main([
        "analyze-offline",
        "--video", str(sample_video),
        "--metadata", str(meta),
        "--transcript", str(transcript_path),
        "--out-dir", str(out),
        "--interim-dir", str(tmp_path / "interim"),
    ])
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["schema_version"] == ANALYSIS_SCHEMA_VERSION
    assert printed["detection"]["status"] == "model_unavailable"
    assert (out / "analysis.json").is_file()


@requires_ffmpeg
def test_demo_flag_never_set_for_offline(sample_video, transcript_path, out_dir, interim):
    doc = analyze_offline_recording(
        sample_video, _meta_single(), transcript=transcript_path,
        out_dir=out_dir, config=PipelineConfig(interim_dir=interim),
    ).to_analysis_dict()
    assert doc["source"] != "demo"
    assert doc["is_synthetic"] is False


def test_no_accidental_recording_apis_in_python_analysis_modules():
    """Guard: offline analysis modules must not reference browser capture APIs."""
    root = Path(__file__).resolve().parents[1] / "src" / "interview_integrity"
    forbidden = ("getUserMedia", "tabCapture", "desktopCapture", "MediaRecorder")
    for path in (
        root / "analysis_contract.py",
        root / "services.py",
        root / "detection" / "boundary.py",
    ):
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{path.name} must not reference {token}"
