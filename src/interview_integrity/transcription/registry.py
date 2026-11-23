"""Create transcribers by name, so callers (CLI, benchmark, future API) stay provider-agnostic."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .adapters.faster_whisper import (
    BASELINE_COMPUTE_TYPE,
    BASELINE_DEVICE,
    BASELINE_MODEL_SIZE,
)
from .base import Transcriber
from .sidecar import SidecarTranscriber

# Approved optional offline baseline. Explicit selection only — never auto-applied.
FASTER_WHISPER_BASELINE_NAME = "faster-whisper-small-int8"
FASTER_WHISPER_BASELINE_OPTIONS: dict[str, Any] = {
    "model_size": BASELINE_MODEL_SIZE,
    "device": BASELINE_DEVICE,
    "compute_type": BASELINE_COMPUTE_TYPE,
    "word_timestamps": True,
    "allow_download": False,
}
# Settings the named baseline always forces (callers may still set download_root / language / …).
_BASELINE_LOCKED = frozenset({"model_size", "device", "compute_type", "word_timestamps"})


def _faster_whisper(**options: Any) -> Transcriber:
    from .adapters.faster_whisper import FasterWhisperTranscriber

    return FasterWhisperTranscriber(**options)


def _faster_whisper_baseline(**options: Any) -> Transcriber:
    """Approved small/CPU/INT8 baseline; core settings cannot be overridden by mistake."""
    from .adapters.faster_whisper import FasterWhisperTranscriber

    merged = {**FASTER_WHISPER_BASELINE_OPTIONS, **options}
    for key in _BASELINE_LOCKED:
        merged[key] = FASTER_WHISPER_BASELINE_OPTIONS[key]
    return FasterWhisperTranscriber(**merged)


def _whisperx(**options: Any) -> Transcriber:
    from .adapters.whisperx import WhisperXTranscriber

    return WhisperXTranscriber(**options)


def _hosted(**options: Any) -> Transcriber:
    from .adapters.hosted import HostedTranscriberPlaceholder

    return HostedTranscriberPlaceholder(**options)


def _sidecar(**options: Any) -> Transcriber:
    return SidecarTranscriber(Path(options["transcript_path"]))


TRANSCRIBERS: dict[str, tuple[Callable[..., Transcriber], str]] = {
    "sidecar": (_sidecar, "load an existing transcript file (option: transcript_path)"),
    FASTER_WHISPER_BASELINE_NAME: (
        _faster_whisper_baseline,
        "optional approved baseline: faster-whisper small / CPU / INT8 + word timestamps "
        "(needs extra 'stt-faster-whisper'; downloads off unless allow_download=true)",
    ),
    "faster-whisper": (
        _faster_whisper,
        "local Whisper via faster-whisper (defaults match the approved baseline; "
        "needs extra 'stt-faster-whisper')",
    ),
    "whisperx": (_whisperx, "candidate: local WhisperX (needs extra 'stt-whisperx'; not approved)"),
    "hosted": (_hosted, "placeholder: requires approved_for_external_upload=true; not implemented"),
}


def create_transcriber(name: str, **options: Any) -> Transcriber:
    try:
        factory, _ = TRANSCRIBERS[name]
    except KeyError:
        raise ValueError(f"Unknown transcriber {name!r}; available: {sorted(TRANSCRIBERS)}") from None
    return factory(**options)


def parse_options(pairs: list[str] | None) -> dict[str, Any]:
    """Parse ``key=value`` strings, converting true/false/none and numbers."""
    out: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"Option must look like key=value, got {pair!r}")
        key, raw = (x.strip() for x in pair.split("=", 1))
        low = raw.lower()
        if low in ("true", "false"):
            value: Any = low == "true"
        elif low in ("none", "null"):
            value = None
        else:
            try:
                value = int(raw)
            except ValueError:
                try:
                    value = float(raw)
                except ValueError:
                    value = raw
        out[key] = value
    return out
