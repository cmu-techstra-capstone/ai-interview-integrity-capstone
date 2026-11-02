"""faster-whisper adapter (local Whisper via CTranslate2).

Approved as the project's **optional** offline STT baseline when explicitly selected:
``small`` / CPU / INT8 with word timestamps. Not the silent default for every
recording — callers must pass a transcriber (CLI ``--stt``, or
``services.resolve_transcriber``).

Optional dependency: ``pip install -e ".[stt-faster-whisper]"`` on a machine with
enough disk. By default weights are **not** downloaded (``allow_download=False``).
Live inference has not been validated on the constrained development laptop;
use teammate validation for real model runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import Segment, Transcriber, Transcript, TranscriptionError, Word
from .base import ModelNotAvailable, import_optional

# Locked defaults for the approved optional baseline (also used by the registry alias).
BASELINE_MODEL_SIZE = "small"
BASELINE_DEVICE = "cpu"
BASELINE_COMPUTE_TYPE = "int8"


class FasterWhisperTranscriber(Transcriber):
    name = "faster-whisper"

    def __init__(
        self,
        model_size: str = BASELINE_MODEL_SIZE,
        *,
        device: str = BASELINE_DEVICE,
        compute_type: str = BASELINE_COMPUTE_TYPE,
        language: str | None = "en",
        word_timestamps: bool = True,
        vad_filter: bool = False,
        initial_prompt: str | None = None,
        beam_size: int = 5,
        download_root: str | None = None,
        allow_download: bool = False,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self.allow_download = allow_download
        self.options = dict(
            language=language,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
            initial_prompt=initial_prompt,
            beam_size=beam_size,
        )
        module = import_optional("faster_whisper", "stt-faster-whisper")
        try:
            self._model = module.WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                download_root=download_root,
                local_files_only=not allow_download,
            )
        except Exception as exc:
            if not allow_download:
                raise ModelNotAvailable(
                    f"faster-whisper model {model_size!r} not found locally (downloads disabled). "
                    "On a machine with disk space, either set allow_download=true once to populate "
                    "the cache, or set download_root to an existing model directory."
                ) from exc
            raise

    def transcribe(self, audio_path: str | Path) -> Transcript:
        try:
            segments, info = self._model.transcribe(str(audio_path), **self.options)
            out = []
            for seg in segments:  # generator: decoding happens while iterating
                words = [
                    Word(
                        text=str(w.word).strip(),
                        start=float(w.start),
                        end=float(w.end),
                        confidence=(
                            float(getattr(w, "probability", None))
                            if getattr(w, "probability", None) is not None
                            else None
                        ),
                    )
                    for w in (getattr(seg, "words", None) or [])
                ]
                out.append(
                    Segment(
                        text=str(seg.text).strip(),
                        start=float(seg.start),
                        end=float(seg.end),
                        words=words,
                    )
                )
            language = getattr(info, "language", None)
            return Transcript(
                segments=out,
                language=language,
                provider=f"faster-whisper:{self.model_size}",
            )
        except TranscriptionError:
            raise
        except Exception as exc:
            # Keep STT failures distinct from EmptyAudioError / audio-quality flags.
            raise TranscriptionError(
                f"faster-whisper transcription failed for {audio_path}: {exc}"
            ) from exc

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model_size": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "download_root": self.download_root,
            "allow_download": self.allow_download,
            **self.options,
        }
