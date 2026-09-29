"""Provider-agnostic transcript model and transcriber interface.

Any speech-to-text backend (local or hosted) should implement ``Transcriber`` and
return a ``Transcript``. Downstream code depends only on these types.

The JSON representation is intentionally compatible with Whisper-style output::

    {"language": "en",
     "segments": [{"start": 0.5, "end": 1.5, "text": "I think so.",
                   "words": [{"word": "I", "start": 0.5, "end": 0.6}, ...]}]}
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class TranscriptionError(RuntimeError):
    pass


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


@dataclass
class Word:
    text: str
    start: float | None = None
    end: float | None = None
    confidence: float | None = None

    @property
    def has_timestamps(self) -> bool:
        return self.start is not None and self.end is not None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Word":
        return cls(
            text=str(d.get("text", d.get("word", ""))).strip(),
            start=_opt_float(d.get("start")),
            end=_opt_float(d.get("end")),
            confidence=_opt_float(d.get("confidence", d.get("probability"))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "start": self.start, "end": self.end, "confidence": self.confidence}


@dataclass
class Segment:
    text: str
    start: float | None = None
    end: float | None = None
    words: list[Word] = field(default_factory=list)
    speaker: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Segment":
        words = [Word.from_dict(w) for w in d.get("words") or []]
        text = str(d.get("text") or " ".join(w.text for w in words)).strip()
        return cls(
            text=text,
            start=_opt_float(d.get("start")),
            end=_opt_float(d.get("end")),
            words=words,
            speaker=d.get("speaker"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "speaker": self.speaker,
            "words": [w.to_dict() for w in self.words],
        }


def _midpoint_in(start: float, end: float, lo: float, hi: float) -> bool:
    return lo <= (start + end) / 2 <= hi


@dataclass
class Transcript:
    segments: list[Segment]
    language: str | None = None
    provider: str | None = None

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments if s.text).strip()

    @property
    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]

    @property
    def has_word_timestamps(self) -> bool:
        words = self.words
        return bool(words) and all(w.has_timestamps for w in words)

    @property
    def has_segment_timestamps(self) -> bool:
        return bool(self.segments) and all(s.start is not None and s.end is not None for s in self.segments)

    def window(self, start: float, end: float) -> "Transcript":
        """Return the part of the transcript falling inside ``[start, end]`` seconds.

        Uses word timestamps when available (a word is kept if its midpoint is in the
        window), otherwise segment timestamps. Raises if there are no timestamps.
        """
        kept: list[Segment] = []
        if self.has_word_timestamps:
            for seg in self.segments:
                words = [w for w in seg.words if _midpoint_in(w.start, w.end, start, end)]  # type: ignore[arg-type]
                if words:
                    kept.append(Segment(
                        text=" ".join(w.text for w in words),
                        start=words[0].start,
                        end=words[-1].end,
                        words=words,
                        speaker=seg.speaker,
                    ))
        elif self.has_segment_timestamps:
            kept = [s for s in self.segments if _midpoint_in(s.start, s.end, start, end)]  # type: ignore[arg-type]
        else:
            raise TranscriptionError("Cannot window a transcript that has no timestamps")
        return Transcript(segments=kept, language=self.language, provider=self.provider)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Transcript":
        if "segments" in d:
            segments = [Segment.from_dict(s) for s in d["segments"]]
        elif d.get("text"):
            segments = [Segment(text=str(d["text"]).strip())]
        else:
            segments = []
        return cls(segments=segments, language=d.get("language"), provider=d.get("provider"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "language": self.language,
            "text": self.text,
            "segments": [s.to_dict() for s in self.segments],
        }


class Transcriber(abc.ABC):
    """Interface every speech-to-text backend implements."""

    name: str = "base"

    @abc.abstractmethod
    def transcribe(self, audio_path: str | Path) -> Transcript:
        """Transcribe ``audio_path`` and return a structured transcript.

        Implementations should include segment and, if possible, word timestamps
        (seconds relative to the start of the audio).
        """
