"""Host / origin guards for the localhost development API."""

from __future__ import annotations

import logging
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import ApiSettings

log = logging.getLogger(__name__)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


def _host_without_port(host_header: str | None) -> str | None:
    if not host_header:
        return None
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6 — not used for this loopback API
        return None
    if ":" in host:
        host = host.rsplit(":", 1)[0]
    return host


class LoopbackHostMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Host header is not loopback (defense in depth)."""

    def __init__(self, app, settings: ApiSettings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self.settings.relax_host_check:
            return await call_next(request)
        host = _host_without_port(request.headers.get("host"))
        if host not in LOOPBACK_HOSTS:
            log.warning("Rejected non-loopback Host header")
            return JSONResponse(
                status_code=403,
                content={"ok": False, "error": {"code": "forbidden_host", "message": "Host not allowed"}},
            )
        return await call_next(request)


class OriginGuardMiddleware(BaseHTTPMiddleware):
    """Reject browser Origins that are not on the configured allowlist.

    Requests with no Origin (e.g. curl, same-machine tooling) are allowed for
    local development. Browser extension / page Origins must match the allowlist
    when configured. If the allowlist is empty, Origins that look like browsers
    are rejected so the operator must configure ``API_ALLOWED_ORIGINS``.
    """

    def __init__(self, app, settings: ApiSettings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("origin")
        if origin is None:
            return await call_next(request)

        allowed = set(self.settings.allowed_origins)
        if origin in allowed:
            return await call_next(request)

        # Always permit same-loopback API tooling if explicitly listed pattern matches
        # http://127.0.0.1:<port> when that exact origin was configured.
        log.warning("Rejected Origin not on allowlist")
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": {
                    "code": "forbidden_origin",
                    "message": "Origin not allowed. Configure INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS "
                    "with your chrome-extension://<id> for local development.",
                },
            },
        )


def client_error(code: str, message: str, status_code: int = 400) -> JSONResponse:
    """Structured error without filesystem paths or stack traces."""
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "error": {"code": code, "message": message}},
    )
