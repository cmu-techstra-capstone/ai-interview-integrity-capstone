"""Live capture/processing session state (in-memory only)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .pcm import PcmChunk


class LiveSessionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class TranscriptUpdate:
    id: str
    text: str
    start_seconds: float
    end_seconds: float
    is_final: bool
    words: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "is_final": self.is_final,
            "words": self.words,
            "speaker": "Candidate",
        }


@dataclass
class LiveSession:
    session_id: str
    created_at: float
    last_activity_at: float
    target_sample_rate: int = 16000
    stt_name: str | None = None
    consent_confirmed: bool = False
    status: str = "active"  # active | stopping | stopped | error
    stt_status: str = "idle"  # idle | ready | unavailable | failed | transcribing
    stt_message: str | None = None
    next_expected_sequence: int = 1
    seen_sequences: set[int] = field(default_factory=set)
    pcm_buffer: bytearray = field(default_factory=bytearray)
    buffered_seconds: float = 0.0
    session_audio_seconds: float = 0.0
    last_inferred_through_seconds: float = 0.0
    transcript_segments: list[TranscriptUpdate] = field(default_factory=list)
    finalized_text: str = ""
    audio_feature_summary: dict[str, Any] = field(default_factory=dict)
    quality_warnings: list[dict[str, str]] = field(default_factory=list)
    bytes_accepted: int = 0
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def create(
        cls,
        *,
        consent_confirmed: bool,
        stt_name: str | None,
        target_sample_rate: int = 16000,
    ) -> "LiveSession":
        if not consent_confirmed:
            raise LiveSessionError("consent_required", "Consent must be confirmed to start a live session")
        now = time.monotonic()
        return cls(
            session_id=str(uuid.uuid4()),
            created_at=now,
            last_activity_at=now,
            target_sample_rate=target_sample_rate,
            stt_name=stt_name,
            consent_confirmed=True,
        )

    def touch(self) -> None:
        self.last_activity_at = time.monotonic()

    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at

    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_activity_at

    def accept_chunk(
        self,
        *,
        sequence: int,
        chunk: PcmChunk,
        max_session_bytes: int,
        client_rel_start_ms: float | None,
    ) -> None:
        if self.status != "active":
            raise LiveSessionError("session_not_active", "Live session is not accepting audio")
        if sequence < 1:
            raise LiveSessionError("invalid_sequence", "sequence must be >= 1")
        if sequence in self.seen_sequences:
            raise LiveSessionError("duplicate_sequence", f"sequence {sequence} already accepted")
        if sequence != self.next_expected_sequence:
            raise LiveSessionError(
                "unexpected_sequence",
                f"Expected sequence {self.next_expected_sequence}, got {sequence}",
            )
        if chunk.sample_rate != self.target_sample_rate:
            raise LiveSessionError(
                "sample_rate_mismatch",
                f"Expected {self.target_sample_rate} Hz mono PCM, got {chunk.sample_rate} Hz",
            )
        if client_rel_start_ms is not None and client_rel_start_ms < -1.0:
            raise LiveSessionError("invalid_timestamp", "client_rel_start_ms cannot be largely negative")

        next_bytes = self.bytes_accepted + len(chunk.samples)
        if next_bytes > max_session_bytes:
            raise LiveSessionError("session_memory_limit", "Live session audio memory limit exceeded")

        self.seen_sequences.add(sequence)
        self.next_expected_sequence = sequence + 1
        self.pcm_buffer.extend(chunk.samples)
        self.buffered_seconds += chunk.duration_seconds
        self.session_audio_seconds += chunk.duration_seconds
        self.bytes_accepted = next_bytes
        self.touch()

    def clear_buffers(self) -> None:
        self.pcm_buffer.clear()
        self.buffered_seconds = 0.0
        self.transcript_segments.clear()
        self.finalized_text = ""
        self.audio_feature_summary.clear()
        self.quality_warnings.clear()
        self.seen_sequences.clear()
        self.next_expected_sequence = 1
        self.last_inferred_through_seconds = 0.0
        self.session_audio_seconds = 0.0
        self.bytes_accepted = 0

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "stt_status": self.stt_status,
            "stt_message": self.stt_message,
            "stt_name": self.stt_name,
            "sample_rate": self.target_sample_rate,
            "session_audio_seconds": round(self.session_audio_seconds, 3),
            "next_expected_sequence": self.next_expected_sequence,
            "transcript_segments": [s.to_dict() for s in self.transcript_segments],
            "audio_feature_summary": dict(self.audio_feature_summary),
            "quality_warnings": list(self.quality_warnings),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "detection": {
                "status": "model_unavailable",
                "message": "Aditi detector is not integrated for live mode yet.",
                "confidence_status": "unavailable_not_calibrated",
            },
        }
