"""Shared fixtures. Media fixtures are generated with ffmpeg at test time (nothing large is committed)."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)

# 4 s clip: 440 Hz tone ("speech") at 0.5-1.5 s and 2.5-3.5 s, silence elsewhere.
TONE_EXPR = "0.5*sin(2*PI*440*t)*(between(t\\,0.5\\,1.5)+between(t\\,2.5\\,3.5))"


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    path = tmp_path_factory.mktemp("media") / "sample.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=4",
        "-f", "lavfi", "-i", f"aevalsrc=exprs={TONE_EXPR}:s=16000:d=4",
        "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(path),
    )
    return path


@pytest.fixture(scope="session")
def silent_video_no_audio(tmp_path_factory) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    path = tmp_path_factory.mktemp("media") / "no_audio.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1", "-c:v", "mpeg4", str(path))
    return path


@pytest.fixture
def invalid_video(tmp_path) -> Path:
    path = tmp_path / "not_a_video.mp4"
    path.write_text("this is not a video")
    return path


def write_tone_wav(path: Path, segments: list[tuple[float, float]], duration: float, rate: int = 16000) -> Path:
    """Pure-Python 16-bit mono WAV with a 440 Hz tone during ``segments``."""
    frames = bytearray()
    for i in range(int(duration * rate)):
        t = i / rate
        on = any(s <= t < e for s, e in segments)
        frames += struct.pack("<h", int(16000 * math.sin(2 * math.pi * 440 * t)) if on else 0)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))
    return path


@pytest.fixture
def metadata_dict() -> dict:
    return {
        "interview_id": "INT001",
        "participant_id": "P001",
        "source_dataset": "staged",
        "question_id": "Q01",
        "question_text": "Why does software testing matter?",
        "assistance_label": "HUMAN_UNASSISTED",
    }


@pytest.fixture
def transcript_path() -> Path:
    return FIXTURES / "sample_transcript.json"


def make_video(path: Path, audio_filter: str | None, duration: float) -> Path:
    """Tiny test video; ``audio_filter`` is an ffmpeg lavfi audio source (None = no audio)."""
    args = ["-f", "lavfi", "-i", f"testsrc=size=160x120:rate=10:duration={duration}"]
    if audio_filter:
        args += ["-f", "lavfi", "-i", audio_filter, "-c:a", "aac", "-shortest"]
    _ffmpeg(*args, "-c:v", "mpeg4", str(path))
    return path


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    return tmp_path_factory.mktemp("media_extra")


@pytest.fixture(scope="session")
def tone_video_2s(media_dir) -> Path:
    return make_video(media_dir / "tone2.mp4", "sine=frequency=300:sample_rate=16000:duration=2", 2)


@pytest.fixture(scope="session")
def noise_only_video(media_dir) -> Path:
    return make_video(media_dir / "noise.mp4", "anoisesrc=color=white:amplitude=0.02:sample_rate=16000:duration=3", 3)


@pytest.fixture(scope="session")
def silent_audio_video(media_dir) -> Path:
    return make_video(media_dir / "silent.mp4", "anullsrc=r=16000:cl=mono:d=2", 2)
