"""Video ingestion: validate a local interview video, record metadata, extract audio.

The original video is never modified or moved. Its SHA-256 is recorded so that
derived artifacts can be traced back to (and checked against) the exact source file.
No visual analysis happens here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..audio.extract import DEFAULT_SAMPLE_RATE, AudioInfo, extract_audio
from ..audio.quality import AudioQuality, validate_audio
from ..datasets.schema import RecordingMetadata
from ..media import InvalidMediaError, ffprobe, first_stream, to_float


@dataclass(frozen=True)
class VideoInfo:
    path: str
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    has_audio: bool
    audio_codec: str | None
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IngestedVideo:
    """Standardized internal representation of one ingested recording."""

    video: VideoInfo
    metadata: RecordingMetadata
    work_dir: Path
    audio: AudioInfo
    audio_quality: AudioQuality
    warnings: list[str]

    @property
    def manifest_path(self) -> Path:
        return self.work_dir / "ingest.json"


def sha256sum(path: str | Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_fps(rate: str | None) -> float | None:
    if not rate or rate == "0/0":
        return None
    if "/" in rate:
        num, den = rate.split("/", 1)
        return round(float(num) / float(den), 3) if float(den) else None
    return to_float(rate)


def probe_video(path: str | Path) -> VideoInfo:
    path = Path(path)
    probe = ffprobe(path)  # raises FileNotFoundError / InvalidMediaError
    video = first_stream(probe, "video")
    if video is None:
        raise InvalidMediaError(f"No video stream found in {path}")
    audio = first_stream(probe, "audio")
    return VideoInfo(
        path=str(path.resolve()),
        duration=to_float(probe.get("format", {}).get("duration")) or to_float(video.get("duration")),
        width=video.get("width"),
        height=video.get("height"),
        fps=_parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        video_codec=video.get("codec_name"),
        has_audio=audio is not None,
        audio_codec=audio.get("codec_name") if audio else None,
        size_bytes=path.stat().st_size,
        sha256=sha256sum(path),
    )


def _safe_dirname(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)


def ingest_video(
    video_path: str | Path,
    metadata: RecordingMetadata | dict[str, Any] | str | Path,
    interim_root: str | Path,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    overwrite: bool = False,
) -> IngestedVideo:
    """Ingest one video into ``<interim_root>/<recording_id>[__<augmentation>]/``.

    Produces ``audio.wav`` and an ``ingest.json`` manifest describing the source
    video, extracted audio, audio quality and recording metadata. If the work dir
    already holds audio from a *different* source file (checksum mismatch), the
    audio is re-extracted rather than reused. Raises ``EmptyAudioError`` if the
    audio track has no usable samples.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if isinstance(metadata, RecordingMetadata):
        meta = metadata
    elif isinstance(metadata, dict):
        meta = RecordingMetadata.from_dict(metadata)
    else:
        meta = RecordingMetadata.from_json(metadata)

    info = probe_video(video_path)
    dirname = meta.recording_id + (f"__{meta.augmentation}" if meta.augmentation else "")
    work_dir = Path(interim_root) / _safe_dirname(dirname)
    work_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = work_dir / "ingest.json"
    if manifest_path.exists() and not overwrite:
        try:
            previous_sha = json.loads(manifest_path.read_text())["video"]["sha256"]
        except (ValueError, KeyError, TypeError):
            previous_sha = None
        overwrite = previous_sha != info.sha256
    elif not manifest_path.exists():
        overwrite = True  # never trust audio left behind without a manifest

    audio = extract_audio(video_path, work_dir / "audio.wav", sample_rate=sample_rate, overwrite=overwrite)
    quality = validate_audio(audio.path)

    warnings = [f"audio {flag.removeprefix('is_')}" for flag in quality.flags]
    if info.duration and audio.duration and abs(info.duration - audio.duration) > 1.0:
        warnings.append(f"audio duration {audio.duration:.2f}s differs from video duration {info.duration:.2f}s")

    ingested = IngestedVideo(
        video=info, metadata=meta, work_dir=work_dir, audio=audio, audio_quality=quality, warnings=warnings
    )
    manifest = {
        "video": info.to_dict(),
        "audio": audio.to_dict(),
        "audio_quality": {**quality.to_features(prefix=""), "duration": quality.duration},
        "warnings": warnings,
        "metadata": {
            "interview_id": meta.interview_id,
            "participant_id": meta.participant_id,
            "recording_id": meta.recording_id,
            "source_dataset": meta.source_dataset.value,
            "augmentation": meta.augmentation,
            "questions": [q.question_id for q in meta.questions],
            "extra": meta.extra,
        },
    }
    ingested.manifest_path.write_text(json.dumps(manifest, indent=2))
    return ingested
