"""WhisperX adapter (faster-whisper + forced alignment + optional diarization). Candidate only.

Unverified against a live install in this repo's CI: WhisperX's API changes between
releases, so validate on a teammate machine. Diarization needs a Hugging Face token
with the pyannote model terms accepted (``hf_token``); without it diarization is skipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import Segment, Transcriber, Transcript, Word
from .base import import_optional


class WhisperXTranscriber(Transcriber):
    name = "whisperx"

    def __init__(
        self,
        model_size: str = "small",
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = "en",
        batch_size: int = 8,
        align: bool = True,
        diarize: bool = False,
        hf_token: str | None = None,
        download_root: str | None = None,
    ):
        self._wx = import_optional("whisperx", "stt-whisperx")
        self.model_size, self.device, self.language = model_size, device, language
        self.batch_size, self.align, self.diarize, self.hf_token = batch_size, align, diarize, hf_token
        self._align_models = {}
        self._model = self._wx.load_model(model_size, device, compute_type=compute_type,
                                          language=language, download_root=download_root)

    def transcribe(self, audio_path: str | Path) -> Transcript:
        wx = self._wx
        audio = wx.load_audio(str(audio_path))
        result = self._model.transcribe(audio, batch_size=self.batch_size)
        language = result.get("language", self.language)
        if self.align:
            if language not in self._align_models:
                self._align_models[language] = wx.load_align_model(language_code=language, device=self.device)
            align_model, meta = self._align_models[language]
            result = wx.align(result["segments"], align_model, meta, audio, self.device,
                              return_char_alignments=False)
        if self.diarize and self.hf_token:
            pipeline_cls = getattr(wx, "DiarizationPipeline", None) or wx.diarize.DiarizationPipeline
            diarization = pipeline_cls(use_auth_token=self.hf_token, device=self.device)(audio)
            result = wx.assign_word_speakers(diarization, result)

        segments = []
        for seg in result["segments"]:
            words = [
                Word(text=str(w.get("word", "")).strip(), start=w.get("start"), end=w.get("end"),
                     confidence=w.get("score"))
                for w in seg.get("words", [])
            ]
            segments.append(Segment(text=str(seg.get("text", "")).strip(), start=seg.get("start"),
                                    end=seg.get("end"), words=words, speaker=seg.get("speaker")))
        return Transcript(segments=segments, language=language, provider=f"whisperx:{self.model_size}")

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "model_size": self.model_size, "align": self.align, "diarize": self.diarize}
