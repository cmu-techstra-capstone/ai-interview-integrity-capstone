"""Deterministic fake transcriber for live tests (no ML packages)."""

from __future__ import annotations

import wave
from pathlib import Path

from ..transcription.base import Segment, Transcript, Word


class FakeLiveTranscriber:
    """Emits fixed words spaced across the WAV duration.

    Useful for end-to-end live chunk → transcript tests without model weights.
    """

    provider = "fake-live"

    def __init__(self, words: tuple[str, ...] = ("hello", "from", "live", "stt")) -> None:
        self._words = words

    def transcribe(self, audio_path: str | Path) -> Transcript:
        path = Path(audio_path)
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 16000
        duration = frames / float(rate) if rate else 0.0
        n = max(1, len(self._words))
        step = duration / n if duration > 0 else 0.1
        words: list[Word] = []
        for i, text in enumerate(self._words):
            start = i * step
            end = min(duration, (i + 1) * step) if duration > 0 else start + 0.1
            words.append(Word(text=text, start=start, end=end, confidence=1.0))
        segment = Segment(
            text=" ".join(self._words),
            start=0.0,
            end=duration if duration > 0 else step * n,
            words=words,
            speaker=None,
        )
        return Transcript(segments=[segment], language="en", provider=self.provider)
