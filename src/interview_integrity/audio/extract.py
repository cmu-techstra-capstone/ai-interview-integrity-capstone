"""Extract a video's audio track into a standard analysis format.

Default output: 16 kHz, mono, 16-bit PCM WAV. This is the common input format for
speech-to-text systems and keeps timing/energy analysis simple.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..media import NoAudioStreamError, ffprobe, first_stream, run_ffmpeg, to_float

DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1


@dataclass(frozen=True)
class AudioInfo:
    path: str
    duration: float | None
    sample_rate: int | None
    channels: int | None
    codec: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def probe_audio(path: str | Path) -> AudioInfo:
    probe = ffprobe(path)
    stream = first_stream(probe, "audio")
    if stream is None:
        raise NoAudioStreamError(f"No audio stream found in {path}")
    duration = to_float(stream.get("duration")) or to_float(probe.get("format", {}).get("duration"))
    sample_rate = to_float(stream.get("sample_rate"))
    return AudioInfo(
        path=str(path),
        duration=duration,
        sample_rate=int(sample_rate) if sample_rate else None,
        channels=stream.get("channels"),
        codec=stream.get("codec_name"),
    )


def extract_audio(
    video_path: str | Path,
    out_path: str | Path,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    overwrite: bool = False,
) -> AudioInfo:
    """Write the audio track of ``video_path`` to ``out_path`` as PCM WAV.

    The source video is only read, never modified. If ``out_path`` exists and
    ``overwrite`` is False, the existing file is reused.
    """
    video_path = Path(video_path)
    out_path = Path(out_path)
    source = ffprobe(video_path)  # raises FileNotFoundError / InvalidMediaError
    if first_stream(source, "audio") is None:
        raise NoAudioStreamError(f"No audio stream found in {video_path}")

    if out_path.exists() and not overwrite:
        return probe_audio(out_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", str(channels),
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        str(out_path),
    ])
    return probe_audio(out_path)
