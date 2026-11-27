"""OpenRouter client (standard library only).

Configuration comes from the environment or a local ``.env`` (see ``.env.example``); the
key is never stored in code, logged or included in ``repr``. Used for research only:
generating controlled AI-written interview answers and rubric scoring. Nothing in the
data pipeline depends on it.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .base import LLMClient, LLMConfigError, LLMResponse

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenRouterError(RuntimeError):
    """The gateway returned an error or an unusable response."""


def load_dotenv(path: str | Path) -> bool:
    """Set missing environment variables from a ``KEY=VALUE`` file. Returns True if read."""
    p = Path(path)
    if not p.is_file():
        return False
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            os.environ.setdefault(key.strip(), value)
    return True


class OpenRouterClient(LLMClient):
    provider = "openrouter"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, *,
                 timeout: float = 120.0, max_retries: int = 4, app_name: str = "cmu-techstra-capstone-research",
                 urlopen: Callable[..., Any] | None = None, sleep: Callable[[float], None] = time.sleep):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.base_url = (base_url or os.environ.get("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        if not self.api_key:
            raise LLMConfigError("OPENROUTER_API_KEY is not set (copy .env.example to .env)")
        self.timeout, self.max_retries, self.app_name = timeout, max_retries, app_name
        self._urlopen = urlopen or urllib.request.urlopen
        self._sleep = sleep

    def __repr__(self) -> str:  # never print the key
        return f"OpenRouterClient(base_url={self.base_url!r})"

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}", "X-Title": self.app_name,
                   "Content-Type": "application/json"}
        last = ""
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
            try:
                with self._urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:300] if hasattr(e, "read") else ""
                last = f"HTTP {e.code}: {detail}"
                if e.code not in RETRY_STATUS:
                    raise OpenRouterError(last) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = f"network error: {e}"
            if attempt < self.max_retries:
                self._sleep(min(60.0, 2.0 ** attempt))
        raise OpenRouterError(f"gave up after {self.max_retries + 1} attempts ({last})")

    def generate(self, prompt, *, model, system=None, temperature=0.7, max_tokens=None,
                 json_mode: bool = False, seed: int | None = None) -> LLMResponse:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if max_tokens:
            body["max_tokens"] = max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if seed is not None:
            body["seed"] = seed
        data = self._request("POST", "/chat/completions", body)
        if "error" in data:
            raise OpenRouterError(f"{model}: {str(data['error'])[:300]}")
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise OpenRouterError(f"{model}: unexpected response shape") from None
        return LLMResponse(text=text, model=data.get("model", model), provider=self.provider,
                           raw={"id": data.get("id"), "usage": data.get("usage")})

    def list_models(self) -> list[str]:
        return sorted(m["id"] for m in self._request("GET", "/models").get("data", []))
