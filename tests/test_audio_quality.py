"""Audio validation and regression tests for audio-pipeline bugs."""

import wave

import pytest

from interview_integrity.audio.extract import extract_audio
from interview_integrity.audio.quality import EmptyAudioError, validate_audio
from interview_integrity.audio.vad import detect_speech_intervals, frame_levels
from interview_integrity.ingestion.video import ingest_video

from .conftest import requires_ffmpeg, write_tone_wav

pytestmark = requires_ffmpeg


def test_validate_clean_tone(tmp_path):
    q = validate_audio(write_tone_wav(tmp_path / "t.wav", [(0.5, 1.5), (2.5, 3.5)], duration=4.0))
    assert q.duration == pytest.approx(4.0)
    assert not q.is_silent and not q.is_noisy and not q.is_clipped
    assert q.snr_db > 60  # digital silence between tones


def test_validate_silent_audio(tmp_path):
    q = validate_audio(write_tone_wav(tmp_path / "s.wav", [], duration=2.0))
    assert q.is_silent and q.flags == ["is_silent"]


def test_validate_empty_audio_raises(tmp_path):
    path = tmp_path / "empty.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000); wf.writeframes(b"")
    with pytest.raises(EmptyAudioError):
        validate_audio(path)


def test_validate_noise_only_is_flagged(noise_only_video, tmp_path):
    q = validate_audio(extract_audio(noise_only_video, tmp_path / "n.wav").path)
    assert q.is_noisy and not q.is_silent


def test_frame_levels_window(tmp_path):
    wav = write_tone_wav(tmp_path / "t.wav", [(0.5, 1.5)], duration=2.0)
    levels = frame_levels(wav, start=1.0, end=2.0)
    assert levels.start == pytest.approx(1.0)
    assert levels.duration == pytest.approx(1.0)


# --- regression: noise-only audio used to be reported as 100% speech
def test_vad_noise_only_reports_no_speech(noise_only_video, tmp_path):
    wav = extract_audio(noise_only_video, tmp_path / "n.wav").path
    assert detect_speech_intervals(wav) == []


# --- regression: a cached WAV with a different sample rate used to be returned as-is
def test_extract_audio_reextracts_on_parameter_change(sample_video, tmp_path):
    out = tmp_path / "a.wav"
    assert extract_audio(sample_video, out).sample_rate == 16000
    assert extract_audio(sample_video, out, sample_rate=8000).sample_rate == 8000
    assert not list(tmp_path.glob("*.partial*"))


# --- regression: re-ingesting a different video under the same recording_id reused stale audio
def test_ingest_reextracts_when_source_changes(sample_video, tone_video_2s, tmp_path):
    meta = {"interview_id": "INT9", "participant_id": "P9", "source_dataset": "staged", "question_id": "Q1"}
    first = ingest_video(sample_video, meta, tmp_path)
    assert first.audio.duration == pytest.approx(4.0, abs=0.1)
    second = ingest_video(tone_video_2s, meta, tmp_path)
    assert second.audio.duration == pytest.approx(2.0, abs=0.1)


def test_ingest_reuses_audio_for_same_source(sample_video, tmp_path):
    meta = {"interview_id": "INT9", "participant_id": "P9", "source_dataset": "staged", "question_id": "Q1"}
    first = ingest_video(sample_video, meta, tmp_path)
    mtime = (first.work_dir / "audio.wav").stat().st_mtime_ns
    ingest_video(sample_video, meta, tmp_path)
    assert (first.work_dir / "audio.wav").stat().st_mtime_ns == mtime


def test_ingest_records_audio_quality_and_warnings(silent_audio_video, tmp_path):
    import json

    meta = {"interview_id": "S1", "participant_id": "P1", "source_dataset": "staged", "question_id": "Q1"}
    ingested = ingest_video(silent_audio_video, meta, tmp_path)
    assert ingested.audio_quality.is_silent
    assert "audio silent" in ingested.warnings
    manifest = json.loads(ingested.manifest_path.read_text())
    assert manifest["audio_quality"]["is_silent"] is True
