"""FastAPI application factory for localhost offline analysis."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..pipeline import PipelineConfig
from ..services import analyze_offline_recording
from .config import ApiSettings
from .paths import PathValidationError, resolve_authorized_file
from .schemas import AnalyzeOfflineRequest, HealthResponse
from .security import LoopbackHostMiddleware, OriginGuardMiddleware, client_error

log = logging.getLogger(__name__)


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings.from_env()

    app = FastAPI(
        title="Interview Integrity Local API",
        version="0.1.0",
        description=(
            "Localhost-only development API for offline interview analysis. "
            "Not a public service. Does not capture Google Meet media."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
        redoc_url=None,
    )
    app.state.api_settings = settings

    # CORS is intentionally narrow and is not authentication.
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Accept"],
            max_age=600,
        )

    app.add_middleware(OriginGuardMiddleware, settings=settings)
    app.add_middleware(LoopbackHostMiddleware, settings=settings)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        root = Path(settings.recordings_dir)
        return HealthResponse(
            recordings_dir_configured=root.is_dir(),
            allowed_origins_configured=bool(settings.allowed_origins),
        )

    @app.post("/v1/analyze-offline")
    def analyze_offline(body: AnalyzeOfflineRequest, request: Request) -> JSONResponse:
        # Log request metadata only — never transcript text or absolute paths.
        log.info(
            "analyze-offline request recording=%s metadata=%s transcript=%s stt=%s",
            body.recording_relpath,
            body.metadata_relpath,
            "set" if body.transcript_relpath else "none",
            body.stt or "none",
        )
        try:
            video = resolve_authorized_file(
                settings,
                body.recording_relpath,
                field="recording_relpath",
                allowed_suffixes=settings.allowed_video_suffixes,
            )
            metadata = resolve_authorized_file(
                settings,
                body.metadata_relpath,
                field="metadata_relpath",
                allowed_suffixes=(".json",),
            )
            transcript: Path | None = None
            if body.transcript_relpath:
                transcript = resolve_authorized_file(
                    settings,
                    body.transcript_relpath,
                    field="transcript_relpath",
                    allowed_suffixes=(".json", ".txt"),
                )
        except PathValidationError as exc:
            status = 404 if exc.code == "file_not_found" else 400
            return client_error(exc.code, exc.message, status_code=status)

        # Ephemeral processing dirs — no retention feature, no upload store.
        with tempfile.TemporaryDirectory(prefix="iic-api-") as tmp:
            tmp_path = Path(tmp)
            interim = tmp_path / "interim"
            out = tmp_path / "out"
            interim.mkdir()
            out.mkdir()
            try:
                result = analyze_offline_recording(
                    video,
                    metadata,
                    transcript=transcript,
                    stt=body.stt,
                    out_dir=out,
                    config=PipelineConfig(interim_dir=interim),
                    write_outputs=False,
                )
            except Exception:  # noqa: BLE001 — never leak internals to clients
                log.exception("analyze-offline unexpected failure")
                return client_error(
                    "internal_error",
                    "Analysis failed due to an internal server error",
                    status_code=500,
                )

        if result.analysis_document is None:
            return client_error("analysis_unavailable", "Analysis document was not produced", status_code=500)

        document: dict[str, Any] = result.to_analysis_dict()
        # Strip absolute filesystem references from sample rows / provenance before responding.
        document = _sanitize_document_for_client(document)

        if result.processing_error:
            # Still return the analysis.v1 envelope so the extension can show failure honestly.
            return JSONResponse(
                status_code=422,
                content={"ok": False, "error": {"code": "processing_failed", "message": "Offline processing failed"}, "analysis": document},
            )

        return JSONResponse(status_code=200, content={"ok": True, "analysis": document})

    return app


def _sanitize_document_for_client(document: dict[str, Any]) -> dict[str, Any]:
    """Remove absolute paths from client-facing analysis JSON."""
    out = dict(document)
    prov = dict(out.get("provenance") or {})
    for key in ("video_path", "metadata_ref", "transcript_path"):
        if key in prov and prov[key]:
            # Keep only the basename so clients cannot learn server layout.
            prov[key] = Path(str(prov[key])).name
    out["provenance"] = prov

    answers = []
    for answer in out.get("answers") or []:
        row = dict(answer)
        sample = dict(row.get("sample_row") or {})
        for key in ("video_reference", "audio_reference", "transcript_path"):
            if key in sample and sample[key]:
                sample[key] = Path(str(sample[key])).name
        row["sample_row"] = sample
        answers.append(row)
    out["answers"] = answers
    return out
