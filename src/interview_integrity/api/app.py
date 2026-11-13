"""FastAPI application factory for localhost offline + live audio analysis."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..live.pcm import PcmError, decode_pcm_s16le_base64
from ..live.processor import LiveProcessor, LiveProcessorConfig
from ..live.session import LiveSession, LiveSessionError
from ..live.store import LiveSessionStore, LiveStoreConfig
from ..pipeline import PipelineConfig
from ..services import analyze_offline_recording
from .config import ApiSettings
from .paths import PathValidationError, resolve_authorized_file
from .schemas import (
    AnalyzeOfflineRequest,
    HealthResponse,
    LiveChunkRequest,
    LiveSessionStartRequest,
)
from .security import LoopbackHostMiddleware, OriginGuardMiddleware, client_error

log = logging.getLogger(__name__)


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings.from_env()

    live_store = LiveSessionStore(
        LiveStoreConfig(
            max_sessions=settings.live_max_sessions,
            session_ttl_seconds=settings.live_session_ttl_seconds,
            idle_ttl_seconds=settings.live_idle_ttl_seconds,
            max_chunk_bytes=settings.live_max_chunk_bytes,
            max_session_bytes=settings.live_max_session_bytes,
            target_sample_rate=16000,
        )
    )
    live_processor = LiveProcessor(
        config=LiveProcessorConfig(default_stt_name=settings.live_default_stt)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        store: LiveSessionStore = app.state.live_store
        store.clear_all()

    app = FastAPI(
        title="Interview Integrity Local API",
        version="0.2.0",
        description=(
            "Localhost-only development API for offline interview analysis and "
            "bounded live Meet tab-audio chunks. Not a public service."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.api_settings = settings
    app.state.live_store = live_store
    app.state.live_processor = live_processor

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
        store: LiveSessionStore = app.state.live_store
        return HealthResponse(
            recordings_dir_configured=root.is_dir(),
            allowed_origins_configured=bool(settings.allowed_origins),
            live_sessions_active=store.active_count(),
            live_audio_enabled=True,
        )

    @app.post("/v1/analyze-offline")
    def analyze_offline(body: AnalyzeOfflineRequest, request: Request) -> JSONResponse:
        del request
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
        document = _sanitize_document_for_client(document)

        if result.processing_error:
            return JSONResponse(
                status_code=422,
                content={
                    "ok": False,
                    "error": {"code": "processing_failed", "message": "Offline processing failed"},
                    "analysis": document,
                },
            )

        return JSONResponse(status_code=200, content={"ok": True, "analysis": document})

    @app.post("/v1/live/sessions")
    def live_start(body: LiveSessionStartRequest) -> JSONResponse:
        store: LiveSessionStore = app.state.live_store
        processor: LiveProcessor = app.state.live_processor
        if not body.consent_confirmed:
            return client_error("consent_required", "Consent must be confirmed before live audio", status_code=400)
        if not body.meet_tab_confirmed:
            return client_error(
                "meet_tab_required",
                "Live sessions require an authorized Google Meet tab affirmation",
                status_code=400,
            )
        try:
            session = LiveSession.create(
                consent_confirmed=True,
                stt_name=body.stt or settings.live_default_stt,
                target_sample_rate=store.config.target_sample_rate,
            )
            store.create(session)
        except LiveSessionError as exc:
            return client_error(exc.code, exc.message, status_code=409 if exc.code == "too_many_sessions" else 400)

        log.info("live session started id=%s stt=%s", session.session_id, session.stt_name)
        payload = processor.build_response(session)
        return JSONResponse(status_code=200, content={"ok": True, "live": payload})

    @app.post("/v1/live/sessions/{session_id}/chunks")
    def live_chunk(session_id: str, body: LiveChunkRequest) -> JSONResponse:
        store: LiveSessionStore = app.state.live_store
        processor: LiveProcessor = app.state.live_processor
        try:
            session = store.get(session_id)
            chunk = decode_pcm_s16le_base64(
                body.pcm_base64,
                sample_rate=body.sample_rate,
                channels=body.channels,
                max_bytes=store.config.max_chunk_bytes,
            )
            if body.duration_ms is not None and abs(body.duration_ms - chunk.duration_ms) > 750:
                # Informational mismatch — reject only extreme lies about duration.
                return client_error(
                    "duration_mismatch",
                    "Declared duration_ms does not match PCM length",
                    status_code=400,
                )
            session.accept_chunk(
                sequence=body.sequence,
                chunk=chunk,
                max_session_bytes=store.config.max_session_bytes,
                client_rel_start_ms=body.client_rel_start_ms,
            )
            live = processor.process_after_chunk(session, force=False)
        except LiveSessionError as exc:
            status = 404 if exc.code == "session_not_found" else 409 if "sequence" in exc.code or exc.code == "duplicate_sequence" else 400
            if exc.code == "unexpected_sequence":
                status = 409
            return client_error(exc.code, exc.message, status_code=status)
        except PcmError as exc:
            return client_error("invalid_audio", str(exc), status_code=400)
        except Exception:  # noqa: BLE001
            log.exception("live chunk processing failed")
            return client_error("internal_error", "Live chunk processing failed", status_code=500)

        # Never log PCM or transcript text.
        log.info(
            "live chunk accepted session=%s seq=%s bytes=%s",
            session_id,
            body.sequence,
            len(chunk.samples),
        )
        return JSONResponse(status_code=200, content={"ok": True, "live": live})

    @app.get("/v1/live/sessions/{session_id}")
    def live_get(session_id: str) -> JSONResponse:
        store: LiveSessionStore = app.state.live_store
        processor: LiveProcessor = app.state.live_processor
        try:
            session = store.get(session_id)
            live = processor.build_response(session)
        except LiveSessionError as exc:
            return client_error(exc.code, exc.message, status_code=404)
        return JSONResponse(status_code=200, content={"ok": True, "live": live})

    @app.post("/v1/live/sessions/{session_id}/stop")
    def live_stop(session_id: str) -> JSONResponse:
        store: LiveSessionStore = app.state.live_store
        processor: LiveProcessor = app.state.live_processor
        try:
            session = store.get(session_id)
            # Final inference flush before buffers are cleared.
            live = processor.process_after_chunk(session, force=True)
            store.stop(session_id)
            live["status"] = "stopped"
            live["transcript_segments"] = live.get("transcript_segments") or []
        except LiveSessionError as exc:
            return client_error(exc.code, exc.message, status_code=404 if exc.code == "session_not_found" else 400)
        log.info("live session stopped id=%s", session_id)
        return JSONResponse(status_code=200, content={"ok": True, "live": live})

    return app


def _sanitize_document_for_client(document: dict[str, Any]) -> dict[str, Any]:
    """Remove absolute paths from client-facing analysis JSON."""
    out = dict(document)
    prov = dict(out.get("provenance") or {})
    for key in ("video_path", "metadata_ref", "transcript_path"):
        if key in prov and prov[key]:
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
