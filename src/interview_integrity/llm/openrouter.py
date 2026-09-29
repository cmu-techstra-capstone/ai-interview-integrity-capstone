"""OpenRouter client placeholder.

Configuration is read from the environment (see ``.env.example``); keys are never
stored in code. The request logic is intentionally not implemented yet — it will be
added when the team starts generating controlled AI-assisted responses.
"""

from __future__ import annotations

import os

from .base import LLMClient, LLMConfigError, LLMResponse

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient(LLMClient):
    provider = "openrouter"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.base_url = base_url or os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)
        if not self.api_key:
            raise LLMConfigError("OPENROUTER_API_KEY is not set (copy .env.example to .env)")

    def __repr__(self) -> str:  # never print the key
        return f"OpenRouterClient(base_url={self.base_url!r})"

    def generate(self, prompt, *, model, system=None, temperature=0.7, max_tokens=None) -> LLMResponse:
        raise NotImplementedError("OpenRouter generation is not implemented yet (out of current MVP scope).")
