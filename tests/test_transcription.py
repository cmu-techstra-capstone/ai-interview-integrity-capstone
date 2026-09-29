import pytest

from interview_integrity.transcription import SidecarTranscriber, Transcript, TranscriptionError


def test_sidecar_json(transcript_path):
    t = SidecarTranscriber(transcript_path).transcribe("ignored.wav")
    assert t.language == "en"
    assert t.has_word_timestamps
    assert len(t.words) == 13
    assert t.text.startswith("Um, I think")
    assert t.provider == "sidecar:sample_transcript.json"


def test_sidecar_txt(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("Plain transcript without timing.")
    t = SidecarTranscriber(p).transcribe()
    assert t.text == "Plain transcript without timing."
    assert not t.has_word_timestamps and not t.has_segment_timestamps


def test_sidecar_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        SidecarTranscriber(tmp_path / "missing.json").transcribe()


def test_sidecar_bad_json(tmp_path):
    p = tmp_path / "t.json"
    p.write_text("{not json")
    with pytest.raises(TranscriptionError):
        SidecarTranscriber(p).transcribe()


def test_sidecar_unsupported_format(tmp_path):
    p = tmp_path / "t.srt"
    p.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi")
    with pytest.raises(TranscriptionError, match="Unsupported"):
        SidecarTranscriber(p).transcribe()


def test_window_by_word_timestamps(transcript_path):
    t = SidecarTranscriber(transcript_path).transcribe()
    second = t.window(2.0, 4.0)
    assert second.text == "You know, it catches bugs early."
    assert len(second.words) == 6


def test_window_without_timestamps_raises():
    with pytest.raises(TranscriptionError):
        Transcript.from_dict({"text": "hello"}).window(0, 1)


def test_roundtrip_dict(transcript_path):
    t = SidecarTranscriber(transcript_path).transcribe()
    again = Transcript.from_dict(t.to_dict())
    assert again.text == t.text and len(again.words) == len(t.words)
