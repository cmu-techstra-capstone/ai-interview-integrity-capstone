"""Disk cache and call budget around any ``LLMClient``.

Every completion is appended to a local JSONL file keyed by a hash of the request, so a
run can be resumed or re-analysed without paying again. The cache holds interview text
and must stay in an ignored ``data/`` path.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

from .base import LLMClient, LLMResponse


class BudgetExceeded(RuntimeError):
    pass


def request_key(**parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class CachedClient(LLMClient):
    def __init__(self, inner: LLMClient, path: str | Path, max_calls: int | None = None):
        self.inner, self.path, self.max_calls = inner, Path(path), max_calls
        self.provider = getattr(inner, "provider", "cached")
        self.calls = self.hits = 0
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}
        if self.path.exists():
            with open(self.path) as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line)
                        self._cache[rec["key"]] = rec

    def __repr__(self) -> str:
        return f"CachedClient({self.inner!r}, entries={len(self._cache)})"

    def generate(self, prompt, *, model, system=None, temperature=0.7, max_tokens=None, **extra) -> LLMResponse:
        key = request_key(model=model, system=system, prompt=prompt, temperature=temperature,
                          max_tokens=max_tokens, **extra)
        with self._lock:
            rec = self._cache.get(key)
            if rec is not None:
                self.hits += 1
                return LLMResponse(rec["text"], rec["model"], self.provider, {"cached": True, "usage": rec.get("usage")})
            if self.max_calls is not None and self.calls >= self.max_calls:
                raise BudgetExceeded(f"max_calls={self.max_calls} reached; rerun to continue (cached calls are free)")
            self.calls += 1
        resp = self.inner.generate(prompt, model=model, system=system, temperature=temperature,
                                   max_tokens=max_tokens, **extra)
        rec = {"key": key, "model_requested": model, "model": resp.model, "text": resp.text,
               "usage": (resp.raw or {}).get("usage"), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with self._lock:
            self._cache[key] = rec
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return resp
