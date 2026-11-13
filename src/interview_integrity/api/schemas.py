"""Pydantic request/response models for the localhost development API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class AnalyzeOfflineRequest(BaseModel):
    """Explicit offline analysis request using relative paths under the recordings root."""

    recording_relpath: str = Field(
        ...,
        description="Relative path to an authorized local recording under RECORDINGS_DIR",
        min_length=1,
        max_length=512,
    )
    metadata_relpath: str = Field(
        ...,
        description="Relative path to recording metadata JSON under RECORDINGS_DIR",
        min_length=1,
        max_length=512,
    )
    transcript_relpath: str | None = Field(
        default=None,
        description="Optional relative sidecar transcript (.json/.txt) under RECORDINGS_DIR",
        max_length=512,
    )
    stt: str | None = Field(
        default=None,
        description="Optional explicit STT registry name; ignored when transcript_relpath is set",
        max_length=128,
    )

    @field_validator("recording_relpath", "metadata_relpath", "transcript_relpath", "stt")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ApiErrorBody(BaseModel):
    code: str
    message: str


class ApiErrorResponse(BaseModel):
    ok: bool = False
    error: ApiErrorBody


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "interview-integrity-api"
    mode: str = "localhost-dev"
    detection_model: str = "unavailable"
    recordings_dir_configured: bool
    allowed_origins_configured: bool
    live_sessions_active: int = 0
    live_audio_enabled: bool = True
    # No filesystem paths returned to clients.


class AnalyzeOfflineResponse(BaseModel):
    ok: bool = True
    analysis: dict[str, Any]


class LiveSessionStartRequest(BaseModel):
    consent_confirmed: bool = False
    stt: str | None = Field(
        default=None,
        description="Optional STT registry name (default faster-whisper-small-int8; use fake-live in tests)",
        max_length=128,
    )
    meet_tab_confirmed: bool = Field(
        default=False,
        description="Client affirms capture targets an authorized Google Meet tab",
    )

    @field_validator("stt")
    @classmethod
    def _strip_stt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LiveChunkRequest(BaseModel):
    sequence: int = Field(..., ge=1)
    sample_rate: int = Field(..., description="PCM sample rate in Hz")
    channels: int = Field(default=1, ge=1, le=2)
    encoding: str = Field(default="pcm_s16le")
    pcm_base64: str = Field(..., min_length=1, max_length=700_000)
    duration_ms: float | None = Field(default=None, ge=0, le=10_000)
    client_rel_start_ms: float | None = Field(
        default=None,
        description="Client-relative start offset (informational; not trusted for ordering)",
    )

    @field_validator("encoding")
    @classmethod
    def _encoding(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned != "pcm_s16le":
            raise ValueError("Only encoding=pcm_s16le is supported")
        return cleaned
