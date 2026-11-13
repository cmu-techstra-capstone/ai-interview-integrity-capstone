"""Bounded in-memory live session store."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .session import LiveSession, LiveSessionError


@dataclass(frozen=True)
class LiveStoreConfig:
    max_sessions: int = 2
    session_ttl_seconds: float = 30 * 60
    idle_ttl_seconds: float = 5 * 60
    max_chunk_bytes: int = 256 * 1024
    max_session_bytes: int = 8 * 1024 * 1024  # ~4+ minutes of 16 kHz mono s16
    target_sample_rate: int = 16000


class LiveSessionStore:
    def __init__(self, config: LiveStoreConfig | None = None) -> None:
        self.config = config or LiveStoreConfig()
        self._sessions: dict[str, LiveSession] = {}
        self._lock = threading.RLock()

    def _expire_locked(self) -> None:
        now = time.monotonic()
        expired = [
            sid
            for sid, sess in self._sessions.items()
            if (now - sess.created_at) > self.config.session_ttl_seconds
            or (now - sess.last_activity_at) > self.config.idle_ttl_seconds
        ]
        for sid in expired:
            sess = self._sessions.pop(sid, None)
            if sess is not None:
                sess.status = "stopped"
                sess.clear_buffers()

    def create(self, session: LiveSession) -> LiveSession:
        with self._lock:
            self._expire_locked()
            if len(self._sessions) >= self.config.max_sessions:
                raise LiveSessionError(
                    "too_many_sessions",
                    f"Maximum concurrent live sessions is {self.config.max_sessions}",
                )
            self._sessions[session.session_id] = session
            return session

    def get(self, session_id: str) -> LiveSession:
        with self._lock:
            self._expire_locked()
            sess = self._sessions.get(session_id)
            if sess is None:
                raise LiveSessionError("session_not_found", "Unknown or expired live session")
            return sess

    def stop(self, session_id: str) -> LiveSession:
        with self._lock:
            sess = self.get(session_id)
            sess.status = "stopped"
            sess.clear_buffers()
            self._sessions.pop(session_id, None)
            return sess

    def clear_all(self) -> None:
        with self._lock:
            for sess in self._sessions.values():
                sess.status = "stopped"
                sess.clear_buffers()
            self._sessions.clear()

    def active_count(self) -> int:
        with self._lock:
            self._expire_locked()
            return len(self._sessions)
