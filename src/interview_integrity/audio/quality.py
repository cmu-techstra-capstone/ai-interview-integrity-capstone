"""Audio validation: catch empty, silent, clipped or very noisy audio explicitly.

``validate_audio`` raises ``EmptyAudioError`` for audio that cannot be analyzed at all
(no samples / near-zero duration). Other problems are reported as flags on
``AudioQuality`` so the dataset quality report can surface them instead of the
pipeline silently producing misleading features.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..media import InvalidMediaError
from .vad import SILENCE_DBFS, FrameLevels, frame_levels

MIN_DURATION_S = 0.25
SILENT_PEAK_DBFS = -60.0  # nothing louder than this anywhere: treat as silent
LOW_SNR_DB = 15.0  # loud frames less than this above the noise floor: noisy / unclear speech
HIGH_CLIPPING_RATIO = 0.01


class EmptyAudioError(InvalidMediaError):
    """The audio track has no usable samples."""


def _db(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


@dataclass(frozen=True)
class AudioQuality:
    duration: float
    peak_dbfs: float | None
    noise_floor_dbfs: float | None  # 10th-percentile frame level
    speech_level_dbfs: float | None  # 95th-percentile frame level
    snr_db: float | None  # speech_level - noise_floor (rough, energy-based)
    clipping_ratio: float
    is_silent: bool
    is_noisy: bool
    is_clipped: bool

    @property
    def flags(self) -> list[str]:
        return [name for name in ("is_silent", "is_noisy", "is_clipped") if getattr(self, name)]

    def to_features(self, prefix: str = "audio_") -> dict[str, Any]:
        return {f"{prefix}{k}": v for k, v in asdict(self).items()}


def assess_levels(levels: FrameLevels) -> AudioQuality:
    peak_dbfs = 20 * math.log10(levels.peak_abs / 32768) if levels.peak_abs > 0 else SILENCE_DBFS
    noise, speech = levels.percentile(0.10), levels.percentile(0.95)
    snr = speech - noise if noise is not None and speech is not None else None
    clipping = levels.clipped_samples / levels.n_samples if levels.n_samples else 0.0
    silent = peak_dbfs < SILENT_PEAK_DBFS
    return AudioQuality(
        duration=round(levels.duration, 3),
        peak_dbfs=_db(peak_dbfs),
        noise_floor_dbfs=_db(noise),
        speech_level_dbfs=_db(speech),
        snr_db=_db(snr),
        clipping_ratio=round(clipping, 5),
        is_silent=silent,
        is_noisy=(not silent) and snr is not None and snr < LOW_SNR_DB,
        is_clipped=clipping > HIGH_CLIPPING_RATIO,
    )


def validate_audio(wav_path: str | Path) -> AudioQuality:
    levels = frame_levels(wav_path)
    if levels.duration < MIN_DURATION_S:
        raise EmptyAudioError(f"Audio has no usable samples (duration {levels.duration:.3f}s): {wav_path}")
    return assess_levels(levels)
