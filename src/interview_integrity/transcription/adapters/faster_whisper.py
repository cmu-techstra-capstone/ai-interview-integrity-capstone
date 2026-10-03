"""faster-whisper adapter (local Whisper via CTranslate2). Candidate only, not the default.

Unverified against a live install in this repo's CI: validate on a teammate machine.
By default, model weights are NOT downloaded (``allow_download=False``): point
``download_root`` at a directory that already contains the model, or opt in explicitly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import Segment, Transcriber, Transcript, Word
from .base import ModelNotAvailable, import_optional


class FasterWhisperTranscriber(Transcriber):
    name = "faster-whisper"

    def __init__(
        self,
        model_size: str = "small",
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = "en",
        word_timestamps: bool = True,
        vad_filter: bool = False,
        initial_prompt: str | None = None,
        beam_size: int = 5,
        download_root: str | None = None,
        allow_download: bool = False,
    ):
        self.model_size = model_size
        self.options = dict(language=language, word_timestamps=word_timestamps, vad_filter=vad_filter,
                            initial_prompt=initial_prompt, beam_size=beam_size)
        module = import_optional("faster_whisper", "stt-faster-whisper")
        try:
            self._model = module.WhisperModel(
                model_size, device=device, compute_type=compute_type,
                download_root=download_root, local_files_only=not allow_download,
            )
        except Exception as exc:
            if not allow_download:
                raise ModelNotAvailable(
                    f"faster-whisper model {model_size!r} not found locally (downloads disabled). "
                    "Run on a machine with disk space with allow_download=true, or set download_root."
                ) from exc
            raise

    def transcribe(self, audio_path: str | Path) -> Transcript:
        segments, info = self._model.transcribe(str(audio_path), **self.options)
        out = []
        for seg in segments:  # generator: decoding happens while iterating
            words = [
                Word(text=str(w.word).strip(), start=float(w.start), end=float(w.end),
                     confidence=float(getattr(w, "probability", None)) if getattr(w, "probability", None) is not None else None)
                for w in (getattr(seg, "words", None) or [])
            ]
            out.append(Segment(text=str(seg.text).strip(), start=float(seg.start), end=float(seg.end), words=words))
        language = getattr(info, "language", None)
        return Transcript(segments=out, language=language, provider=f"faster-whisper:{self.model_size}")

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "model_size": self.model_size, **self.options}
