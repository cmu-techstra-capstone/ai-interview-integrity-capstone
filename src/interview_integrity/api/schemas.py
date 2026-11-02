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
    # No filesystem paths returned to clients.


class AnalyzeOfflineResponse(BaseModel):
    ok: bool = True
    analysis: dict[str, Any]
