"""Thin wrappers around the ffmpeg / ffprobe command-line tools."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class MediaError(RuntimeError):
    """Base class for media-processing failures."""


class MissingDependencyError(MediaError):
    """A required external binary (ffmpeg/ffprobe) is not installed."""


class InvalidMediaError(MediaError):
    """The file exists but cannot be decoded as the expected media type."""


class NoAudioStreamError(InvalidMediaError):
    """The video has no audio track to extract."""


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise MissingDependencyError(
            f"'{name}' was not found on PATH. Install ffmpeg (macOS: `brew install ffmpeg`, "
            "Ubuntu: `sudo apt install ffmpeg`)."
        )
    return path


def ffprobe(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Media file not found: {path}")
    cmd = [
        require_binary("ffprobe"),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise InvalidMediaError(f"ffprobe could not read {path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def run_ffmpeg(args: list[str]) -> None:
    cmd = [require_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise MediaError(f"ffmpeg failed ({' '.join(args)}): {result.stderr.strip()}")


def first_stream(probe: dict[str, Any], codec_type: str) -> dict[str, Any] | None:
    return next((s for s in probe.get("streams", []) if s.get("codec_type") == codec_type), None)


def to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
