"""Live STT windowing, deduplication, and research-status assembly."""

from __future__ import annotations

import logging
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..transcription.adapters.base import MissingOptionalDependency, ModelNotAvailable
from ..transcription.base import Transcript, Transcriber
from ..transcription.registry import FASTER_WHISPER_BASELINE_NAME, create_transcriber
from .audio_features import summarize_speech_window
from .fake_stt import FakeLiveTranscriber
from .pcm import write_wav_bytes
from .research import AudioDeliveryResearchAdapter, TranscriptAuthorshipResearchAdapter
from .session import LiveSession, LiveSessionError, TranscriptUpdate

log = logging.getLogger(__name__)


class TranscriberFactory(Protocol):
    def __call__(self, name: str | None) -> Transcriber: ...


@dataclass(frozen=True)
class LiveProcessorConfig:
    # Transport chunks are ~1–2 s; inference uses a larger accumulated window.
    min_infer_seconds: float = 4.0
    target_window_seconds: float = 8.0
    overlap_seconds: float = 2.0
    max_infer_seconds: float = 12.0
    default_stt_name: str = FASTER_WHISPER_BASELINE_NAME


def default_transcriber_factory(name: str | None) -> Transcriber:
    if name == "fake-live" or name == "fake":
        return FakeLiveTranscriber()
    selected = name or FASTER_WHISPER_BASELINE_NAME
    return create_transcriber(selected)


class LiveProcessor:
    def __init__(
        self,
        *,
        config: LiveProcessorConfig | None = None,
        transcriber_factory: TranscriberFactory | None = None,
        audio_research: AudioDeliveryResearchAdapter | None = None,
        text_research: TranscriptAuthorshipResearchAdapter | None = None,
    ) -> None:
        self.config = config or LiveProcessorConfig()
        self._factory = transcriber_factory or default_transcriber_factory
        self._audio_research = audio_research or AudioDeliveryResearchAdapter()
        self._text_research = text_research or TranscriptAuthorshipResearchAdapter()
        self._transcribers: dict[str, Transcriber] = {}

    def _get_transcriber(self, session: LiveSession) -> Transcriber | None:
        name = session.stt_name or self.config.default_stt_name
        if name in self._transcribers:
            return self._transcribers[name]
        try:
            tr = self._factory(name)
            self._transcribers[name] = tr
            session.stt_status = "ready"
            session.stt_message = f"STT ready ({name})"
            return tr
        except MissingOptionalDependency as exc:
            session.stt_status = "unavailable"
            session.stt_message = str(exc) or "STT optional dependency is not installed"
            return None
        except ModelNotAvailable as exc:
            session.stt_status = "unavailable"
            session.stt_message = str(exc) or "STT model weights are not available locally"
            return None
        except Exception as exc:  # noqa: BLE001
            session.stt_status = "failed"
            session.stt_message = f"STT initialization failed: {type(exc).__name__}"
            log.exception("live STT init failed")
            return None

    def process_after_chunk(self, session: LiveSession, *, force: bool = False) -> dict[str, Any]:
        """Possibly run STT on the accumulated window; always return a live update payload."""
        new_audio = session.session_audio_seconds - session.last_inferred_through_seconds
        should_run = force or new_audio >= self.config.min_infer_seconds
        if should_run and session.pcm_buffer:
            self._run_inference(session, force=force)

        return self.build_response(session)

    def build_response(self, session: LiveSession) -> dict[str, Any]:
        speech_seconds = float(session.audio_feature_summary.get("speech_seconds") or 0.0)
        transcript_text = " ".join(s.text for s in session.transcript_segments if s.is_final).strip()
        if not transcript_text:
            transcript_text = " ".join(s.text for s in session.transcript_segments).strip()

        audio_research = self._audio_research.infer(
            speech_seconds=speech_seconds,
            feature_summary=session.audio_feature_summary or None,
        )
        text_research = self._text_research.infer(transcript_text=transcript_text)

        snap = session.public_snapshot()
        snap["audio_research"] = audio_research.to_dict()
        snap["transcript_research"] = text_research.to_dict()
        snap["backend"] = {"connected": True}
        return snap

    def _run_inference(self, session: LiveSession, *, force: bool) -> None:
        tr = self._get_transcriber(session)
        if tr is None:
            return

        rate = session.target_sample_rate
        bytes_per_sec = rate * 2
        total_seconds = len(session.pcm_buffer) / float(bytes_per_sec)
        if total_seconds <= 0:
            return

        window_seconds = min(self.config.target_window_seconds, total_seconds)
        if force:
            window_seconds = min(self.config.max_infer_seconds, total_seconds)
        window_bytes = int(window_seconds * bytes_per_sec)
        # Align to sample boundary.
        window_bytes -= window_bytes % 2
        if window_bytes <= 0:
            return

        pcm_window = bytes(session.pcm_buffer[-window_bytes:])
        window_start = max(0.0, total_seconds - window_seconds)

        session.stt_status = "transcribing"
        try:
            with tempfile.TemporaryDirectory(prefix="iic-live-stt-") as tmp:
                wav_path = Path(tmp) / "chunk.wav"
                wav_path.write_bytes(write_wav_bytes(pcm_window, sample_rate=rate, channels=1))
                transcript = tr.transcribe(wav_path)
        except ModelNotAvailable as exc:
            session.stt_status = "unavailable"
            session.stt_message = str(exc) or "STT model unavailable"
            return
        except Exception:  # noqa: BLE001
            session.stt_status = "failed"
            session.stt_message = "Transcription failed"
            log.exception("live transcription failed")
            return

        session.audio_feature_summary = summarize_speech_window(
            pcm_window,
            sample_rate=rate,
            session_offset_seconds=window_start,
        )
        self._merge_transcript(session, transcript, window_start=window_start)
        session.last_inferred_through_seconds = session.session_audio_seconds
        session.stt_status = "ready"
        session.stt_message = "Transcription updated"

        # Bound RAM: keep only the overlap tail after a successful inference.
        keep_seconds = self.config.overlap_seconds
        keep_bytes = int(keep_seconds * bytes_per_sec)
        keep_bytes -= keep_bytes % 2
        if len(session.pcm_buffer) > keep_bytes > 0:
            tail = bytes(session.pcm_buffer[-keep_bytes:])
            session.pcm_buffer.clear()
            session.pcm_buffer.extend(tail)
            session.buffered_seconds = keep_seconds

    def _merge_transcript(self, session: LiveSession, transcript: Transcript, *, window_start: float) -> None:
        words = []
        for seg in transcript.segments:
            if seg.words:
                for w in seg.words:
                    if not w.text:
                        continue
                    local_start = float(w.start if w.start is not None else 0.0)
                    local_end = float(w.end if w.end is not None else local_start)
                    words.append(
                        {
                            "text": w.text.strip(),
                            "start": round(window_start + local_start, 3),
                            "end": round(window_start + local_end, 3),
                        }
                    )
            elif seg.text:
                local_start = float(seg.start if seg.start is not None else 0.0)
                local_end = float(seg.end if seg.end is not None else local_start)
                words.append(
                    {
                        "text": seg.text.strip(),
                        "start": round(window_start + local_start, 3),
                        "end": round(window_start + local_end, 3),
                    }
                )

        if not words:
            if not session.quality_warnings:
                session.quality_warnings.append(
                    {"id": "live-silence", "code": "silence_or_empty", "message": "No speech recognized in the latest window."}
                )
            return

        # Drop quality silence warning once we have words.
        session.quality_warnings = [w for w in session.quality_warnings if w.get("code") != "silence_or_empty"]

        # Deduplicate against already finalized text using a simple suffix/prefix check.
        new_tokens = [w["text"] for w in words if w["text"]]
        existing = session.finalized_text.split()
        deduped = _dedupe_token_suffix(existing, new_tokens)
        if not deduped:
            return

        # Keep only word metadata for the deduped suffix.
        keep_n = len(deduped)
        kept_words = words[-keep_n:] if keep_n <= len(words) else words
        text = " ".join(deduped)
        start = float(kept_words[0]["start"])
        end = float(kept_words[-1]["end"])
        update = TranscriptUpdate(
            id=f"live-{uuid.uuid4().hex[:10]}",
            text=text,
            start_seconds=start,
            end_seconds=end,
            is_final=True,
            words=kept_words,
        )
        session.transcript_segments.append(update)
        # Bound segment list growth.
        if len(session.transcript_segments) > 200:
            session.transcript_segments = session.transcript_segments[-200:]
        session.finalized_text = (session.finalized_text + " " + text).strip()


def _dedupe_token_suffix(existing: list[str], incoming: list[str]) -> list[str]:
    """Remove overlapping prefix of ``incoming`` that matches a suffix of ``existing``."""
    if not incoming:
        return []
    if not existing:
        return incoming
    max_k = min(len(existing), len(incoming))
    for k in range(max_k, 0, -1):
        if [t.lower() for t in existing[-k:]] == [t.lower() for t in incoming[:k]]:
            return incoming[k:]
    return incoming


def ensure_active(session: LiveSession) -> None:
    if session.status != "active":
        raise LiveSessionError("session_not_active", "Live session is not active")
