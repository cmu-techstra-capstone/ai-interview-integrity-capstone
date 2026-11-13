"""Development API settings (environment-driven; loopback-only by design)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

PREFIX = "INTERVIEW_INTEGRITY_"

# Fixed development defaults — not a public deployment profile.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
ALLOWED_BIND_HOSTS = frozenset({"127.0.0.1", "localhost"})


class ApiConfigError(ValueError):
    pass


def _parse_origins(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return ()
    parts = []
    for item in raw.split(","):
        origin = item.strip()
        if not origin:
            continue
        if origin != "*" and not (
            origin.startswith("chrome-extension://")
            or origin.startswith("http://127.0.0.1")
            or origin.startswith("http://localhost")
        ):
            raise ApiConfigError(
                f"Disallowed CORS origin {origin!r}. Use chrome-extension://<id> "
                "and/or http://127.0.0.1:<port> for local development only."
            )
        if origin == "*":
            raise ApiConfigError("Wildcard CORS origin '*' is not allowed for this API")
        parts.append(origin)
    return tuple(parts)


@dataclass(frozen=True)
class ApiSettings:
    """Settings for the localhost development API."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    recordings_dir: Path = Path("data/authorized_recordings")
    interim_dir: Path = Path("data/interim")
    out_dir: Path = Path("data/processed")
    allowed_origins: tuple[str, ...] = ()
    # When True, TestClient / unit tests may skip Host header enforcement.
    relax_host_check: bool = False
    # Live session limits (in-memory only; no disk retention).
    live_max_sessions: int = 2
    live_max_chunk_bytes: int = 256 * 1024
    live_max_session_bytes: int = 8 * 1024 * 1024
    live_session_ttl_seconds: float = 30 * 60
    live_idle_ttl_seconds: float = 5 * 60
    live_default_stt: str = "faster-whisper-small-int8"
    allowed_video_suffixes: tuple[str, ...] = (
        ".mp4",
        ".mov",
        ".mkv",
        ".webm",
        ".m4v",
        ".avi",
        ".wav",
    )

    def __post_init__(self) -> None:
        if self.host not in ALLOWED_BIND_HOSTS:
            raise ApiConfigError(
                f"API host must be loopback ({sorted(ALLOWED_BIND_HOSTS)}), got {self.host!r}"
            )
        if not (1 <= self.port <= 65535):
            raise ApiConfigError(f"Invalid API port: {self.port}")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ApiSettings":
        env = os.environ if env is None else env

        def get(name: str) -> str | None:
            value = env.get(PREFIX + name.upper())
            return value.strip() if value and value.strip() else None

        host = get("api_host") or DEFAULT_HOST
        if host not in ALLOWED_BIND_HOSTS:
            raise ApiConfigError(
                f"{PREFIX}API_HOST must be loopback-only; refused {host!r}"
            )

        port_raw = get("api_port")
        try:
            port = int(port_raw) if port_raw else DEFAULT_PORT
        except ValueError as exc:
            raise ApiConfigError(f"{PREFIX}API_PORT must be an integer") from exc

        relax = (get("api_relax_host_check") or "").lower() in {"1", "true", "yes"}

        def _int(name: str, default: int) -> int:
            raw = get(name)
            if not raw:
                return default
            try:
                return int(raw)
            except ValueError as exc:
                raise ApiConfigError(f"{PREFIX}{name.upper()} must be an integer") from exc

        def _float(name: str, default: float) -> float:
            raw = get(name)
            if not raw:
                return default
            try:
                return float(raw)
            except ValueError as exc:
                raise ApiConfigError(f"{PREFIX}{name.upper()} must be a number") from exc

        return cls(
            host=host,
            port=port,
            recordings_dir=Path(get("recordings_dir") or cls.recordings_dir),
            interim_dir=Path(get("api_interim_dir") or get("interim_dir") or cls.interim_dir),
            out_dir=Path(get("api_out_dir") or get("out_dir") or cls.out_dir),
            allowed_origins=_parse_origins(get("api_allowed_origins")),
            relax_host_check=relax,
            live_max_sessions=_int("live_max_sessions", cls.live_max_sessions),
            live_max_chunk_bytes=_int("live_max_chunk_bytes", cls.live_max_chunk_bytes),
            live_max_session_bytes=_int("live_max_session_bytes", cls.live_max_session_bytes),
            live_session_ttl_seconds=_float("live_session_ttl_seconds", cls.live_session_ttl_seconds),
            live_idle_ttl_seconds=_float("live_idle_ttl_seconds", cls.live_idle_ttl_seconds),
            live_default_stt=(get("live_default_stt") or cls.live_default_stt),
        )

    @property
    def public_base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
