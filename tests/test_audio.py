import pytest

from interview_integrity.audio.extract import extract_audio, probe_audio
from interview_integrity.audio.vad import detect_speech_intervals

from .conftest import requires_ffmpeg, write_tone_wav


@requires_ffmpeg
def test_extract_audio_standard_format(sample_video, tmp_path):
    info = extract_audio(sample_video, tmp_path / "a.wav")
    assert info.sample_rate == 16000
    assert info.channels == 1
    assert info.codec == "pcm_s16le"
    assert info.duration == pytest.approx(4.0, abs=0.1)


@requires_ffmpeg
def test_extract_audio_custom_rate(sample_video, tmp_path):
    info = extract_audio(sample_video, tmp_path / "a.wav", sample_rate=8000)
    assert info.sample_rate == 8000


@requires_ffmpeg
def test_extract_audio_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_audio(tmp_path / "missing.mp4", tmp_path / "a.wav")


@requires_ffmpeg
def test_probe_audio_reads_wav(tmp_path):
    wav = write_tone_wav(tmp_path / "t.wav", [(0.0, 0.5)], duration=1.0)
    info = probe_audio(wav)
    assert info.sample_rate == 16000 and info.channels == 1


def test_vad_detects_tone_segments(tmp_path):
    wav = write_tone_wav(tmp_path / "t.wav", [(0.5, 1.5), (2.5, 3.5)], duration=4.0)
    intervals = detect_speech_intervals(wav)
    assert len(intervals) == 2
    for (s, e), (es, ee) in zip(intervals, [(0.5, 1.5), (2.5, 3.5)]):
        assert s == pytest.approx(es, abs=0.05)
        assert e == pytest.approx(ee, abs=0.05)


def test_vad_respects_window(tmp_path):
    wav = write_tone_wav(tmp_path / "t.wav", [(0.5, 1.5), (2.5, 3.5)], duration=4.0)
    intervals = detect_speech_intervals(wav, start=2.0, end=4.0)
    assert len(intervals) == 1
    assert intervals[0][0] == pytest.approx(2.5, abs=0.05)


def test_vad_silence_returns_empty(tmp_path):
    wav = write_tone_wav(tmp_path / "t.wav", [], duration=1.0)
    assert detect_speech_intervals(wav) == []


def test_vad_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        detect_speech_intervals(tmp_path / "missing.wav")


def test_vad_adapts_to_quiet_recordings(tmp_path):
    """A recording ~40 dB quieter than usual is still segmented correctly by the adaptive threshold."""
    import math, struct, wave
    path = tmp_path / "quiet.wav"
    rate = 16000
    frames = bytearray()
    for i in range(3 * rate):
        t = i / rate
        on = 1.0 <= t < 2.0
        # speech ~ -46 dBFS, background noise ~ -80 dBFS
        v = 160 * math.sin(2 * math.pi * 440 * t) if on else 3 * math.sin(2 * math.pi * 97 * t)
        frames += struct.pack("<h", int(v))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate); wf.writeframes(bytes(frames))

    assert detect_speech_intervals(path, threshold_dbfs=-40.0) == []  # old fixed threshold misses it
    [(s, e)] = detect_speech_intervals(path)
    assert s == pytest.approx(1.0, abs=0.05) and e == pytest.approx(2.0, abs=0.05)
