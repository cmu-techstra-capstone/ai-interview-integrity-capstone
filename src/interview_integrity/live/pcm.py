"""PCM / WAV helpers for live chunks (stdlib only)."""

from __future__ import annotations

import base64
import io
import wave
from dataclasses import dataclass


class PcmError(ValueError):
    pass


@dataclass(frozen=True)
class PcmChunk:
    sample_rate: int
    channels: int
    samples: bytes  # little-endian signed 16-bit interleaved
    duration_ms: float

    @property
    def frame_count(self) -> int:
        width = 2 * self.channels
        if width <= 0 or len(self.samples) % width != 0:
            return 0
        return len(self.samples) // width

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.frame_count / float(self.sample_rate)


def decode_pcm_s16le_base64(
    payload_b64: str,
    *,
    sample_rate: int,
    channels: int,
    max_bytes: int,
) -> PcmChunk:
    if sample_rate not in {8000, 16000, 22050, 24000, 32000, 44100, 48000}:
        raise PcmError(f"Unsupported sample_rate: {sample_rate}")
    if channels != 1:
        raise PcmError("Only mono (channels=1) is accepted for live chunks")
    if not payload_b64 or not isinstance(payload_b64, str):
        raise PcmError("pcm_base64 is required")
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise PcmError("pcm_base64 is not valid base64") from exc
    if len(raw) == 0:
        raise PcmError("Empty PCM payload")
    if len(raw) > max_bytes:
        raise PcmError(f"PCM payload exceeds max_bytes={max_bytes}")
    if len(raw) % 2 != 0:
        raise PcmError("PCM payload byte length must be even for s16le")
    frame_count = len(raw) // 2
    duration_ms = (frame_count / float(sample_rate)) * 1000.0
    return PcmChunk(
        sample_rate=sample_rate,
        channels=channels,
        samples=raw,
        duration_ms=duration_ms,
    )


def write_wav_bytes(pcm: bytes, *, sample_rate: int, channels: int = 1) -> bytes:
    """Encode PCM s16le into an in-memory WAV container."""
    if channels < 1:
        raise PcmError("channels must be >= 1")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def read_wav_pcm(path_or_bytes: bytes | str) -> tuple[bytes, int, int]:
    """Return (pcm_s16le, sample_rate, channels) from a WAV file or bytes."""
    if isinstance(path_or_bytes, bytes):
        src: io.BufferedIOBase = io.BytesIO(path_or_bytes)
    else:
        src = open(path_or_bytes, "rb")  # noqa: SIM115
    try:
        with wave.open(src, "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            if width != 2:
                raise PcmError("Only 16-bit WAV is supported")
            frames = wf.readframes(wf.getnframes())
            return frames, rate, channels
    finally:
        if not isinstance(path_or_bytes, bytes):
            src.close()
