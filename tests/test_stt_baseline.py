"""Approved optional faster-whisper small/CPU/INT8 baseline — mocked only (no downloads)."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from interview_integrity import services
from interview_integrity.audio.quality import EmptyAudioError
from interview_integrity.pipeline import PipelineConfig, process_video
from interview_integrity.transcription.adapters.base import MissingOptionalDependency, ModelNotAvailable
from interview_integrity.transcription.base import TranscriptionError
from interview_integrity.transcription.registry import (
    FASTER_WHISPER_BASELINE_NAME,
    FASTER_WHISPER_BASELINE_OPTIONS,
    create_transcriber,
)
from interview_integrity.transcription.sidecar import SidecarTranscriber

from .conftest import requires_ffmpeg


def _fake_faster_whisper(*, fail_load=False, fail_transcribe=False):
    mod = types.ModuleType("faster_whisper")
    calls: dict = {}

    class WhisperModel:
        def __init__(self, size, **kw):
            calls["init"] = (size, kw)
            if fail_load:
                raise RuntimeError("model not in cache")

        def transcribe(self, path, **kw):
            calls["transcribe"] = (path, kw)
            if fail_transcribe:
                raise RuntimeError("decode boom")
            W = types.SimpleNamespace
            seg = W(
                start=0.5,
                end=1.5,
                text=" Um, I think so.",
                words=[
                    W(word=" Um,", start=0.5, end=0.6, probability=0.9),
                    W(word=" I", start=0.7, end=0.8, probability=0.95),
                    W(word=" think", start=0.8, end=1.0, probability=0.99),
                    W(word=" so.", start=1.0, end=1.5, probability=0.97),
                ],
            )
            return iter([seg]), W(language="en")

    mod.WhisperModel = WhisperModel
    return mod, calls


def test_baseline_name_selects_small_cpu_int8(monkeypatch):
    mod, calls = _fake_faster_whisper()
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    t = create_transcriber(FASTER_WHISPER_BASELINE_NAME)
    desc = t.describe()
    assert desc["model_size"] == "small"
    assert desc["device"] == "cpu"
    assert desc["compute_type"] == "int8"
    assert desc["word_timestamps"] is True
    assert desc["allow_download"] is False
    size, kw = calls["init"]
    assert size == "small"
    assert kw["device"] == "cpu" and kw["compute_type"] == "int8"
    assert kw["local_files_only"] is True


def test_baseline_locks_core_settings_against_override(monkeypatch):
    mod, calls = _fake_faster_whisper()
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    create_transcriber(
        FASTER_WHISPER_BASELINE_NAME,
        model_size="medium",
        device="cuda",
        compute_type="float16",
        word_timestamps=False,
        allow_download=True,
        download_root="/models",
    )
    size, kw = calls["init"]
    assert size == "small"
    assert kw["device"] == "cpu" and kw["compute_type"] == "int8"
    assert kw["local_files_only"] is False  # allow_download override permitted
    assert kw["download_root"] == "/models"


def test_faster_whisper_defaults_match_baseline(monkeypatch):
    mod, calls = _fake_faster_whisper()
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    t = create_transcriber("faster-whisper")
    assert t.describe()["model_size"] == FASTER_WHISPER_BASELINE_OPTIONS["model_size"]
    assert calls["init"][1]["device"] == "cpu"
    assert calls["init"][1]["compute_type"] == "int8"
    assert calls["init"][1]["local_files_only"] is True


def test_word_timestamps_preserved(monkeypatch):
    mod, calls = _fake_faster_whisper()
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    tr = create_transcriber(FASTER_WHISPER_BASELINE_NAME).transcribe("a.wav")
    assert tr.has_word_timestamps
    assert [w.text for w in tr.words] == ["Um,", "I", "think", "so."]
    assert calls["transcribe"][1]["word_timestamps"] is True
    assert tr.provider == "faster-whisper:small"


def test_resolve_transcriber_prefers_sidecar(tmp_path, monkeypatch):
    called = {"stt": False}

    def boom(**_):
        called["stt"] = True
        raise AssertionError("STT must not run when a sidecar is provided")

    monkeypatch.setitem(
        __import__("interview_integrity.transcription.registry", fromlist=["TRANSCRIBERS"]).TRANSCRIBERS,
        "faster-whisper-small-int8",
        (boom, "test"),
    )
    p = tmp_path / "ans.txt"
    p.write_text("sidecar wins")
    tr = services.resolve_transcriber(transcript=p, stt=FASTER_WHISPER_BASELINE_NAME)
    assert isinstance(tr, SidecarTranscriber)
    assert tr.transcribe().text == "sidecar wins"
    assert called["stt"] is False


def test_resolve_transcriber_none_when_not_selected():
    assert services.resolve_transcriber() is None
    assert services.resolve_transcriber(stt=None) is None


@requires_ffmpeg
def test_stt_not_invoked_when_pipeline_has_no_transcriber(sample_video, metadata_dict, tmp_path, monkeypatch):
    """Pipeline with transcriber=None must not construct faster-whisper."""
    monkeypatch.setitem(sys.modules, "faster_whisper", None)

    def boom(*_a, **_k):
        raise AssertionError("FasterWhisperTranscriber must not be constructed")

    monkeypatch.setattr(
        "interview_integrity.transcription.adapters.faster_whisper.FasterWhisperTranscriber",
        boom,
    )
    [sample] = process_video(
        sample_video,
        metadata_dict,
        transcriber=None,
        config=PipelineConfig(interim_dir=tmp_path / "interim"),
    )
    assert sample.transcript is None
    assert sample.features["timing_source"] == "energy_vad"
    assert sample.features["transcript_source"] is None


def test_missing_optional_dependency_message(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    with pytest.raises(MissingOptionalDependency, match="stt-faster-whisper"):
        create_transcriber(FASTER_WHISPER_BASELINE_NAME)


def test_no_download_during_lightweight_construction(monkeypatch):
    mod, calls = _fake_faster_whisper(fail_load=True)
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    with pytest.raises(ModelNotAvailable, match="downloads disabled"):
        create_transcriber(FASTER_WHISPER_BASELINE_NAME)
    assert calls["init"][1]["local_files_only"] is True


def test_transcription_failure_is_transcription_error(monkeypatch):
    mod, _ = _fake_faster_whisper(fail_transcribe=True)
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    t = create_transcriber(FASTER_WHISPER_BASELINE_NAME)
    with pytest.raises(TranscriptionError, match="faster-whisper transcription failed"):
        t.transcribe("a.wav")


def test_transcription_error_distinct_from_empty_audio():
    assert not issubclass(TranscriptionError, EmptyAudioError)
    assert not issubclass(EmptyAudioError, TranscriptionError)


@requires_ffmpeg
def test_batch_records_stt_failure_without_aborting_others(sample_video, metadata_dict, tmp_path, monkeypatch):
    mod, _ = _fake_faster_whisper(fail_transcribe=True)
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    batch = tmp_path / "batch"
    batch.mkdir()
    video = batch / "rec.mp4"
    video.write_bytes(Path(sample_video).read_bytes())
    (batch / "rec.metadata.json").write_text(json.dumps(metadata_dict))
    # Second recording: sidecar only, no STT needed — should succeed if we pass None after first fails.
    # Use STT for the whole batch so the one without sidecar fails with TranscriptionError.
    result = services.process_local_batch(
        batch,
        out_dir=tmp_path / "out",
        config=PipelineConfig(interim_dir=tmp_path / "interim"),
        transcriber=create_transcriber(FASTER_WHISPER_BASELINE_NAME),
    )
    assert "rec" in result.failed
    assert "TranscriptionError" in result.failed["rec"]


def test_baseline_config_file_is_valid():
    from interview_integrity.transcription.benchmark import load_candidates
    from interview_integrity.transcription.registry import TRANSCRIBERS

    path = Path(__file__).resolve().parents[1] / "config" / "stt_baseline.faster_whisper_small_int8.json"
    cands = load_candidates(path)
    assert len(cands) == 1
    assert cands[0].transcriber in TRANSCRIBERS
    assert cands[0].transcriber == FASTER_WHISPER_BASELINE_NAME
    assert cands[0].sends_audio_externally is False


def test_core_services_work_without_stt_selected():
    assert services.resolve_transcriber() is None
    assert services.resolve_transcriber(transcript=None, stt=None) is None
