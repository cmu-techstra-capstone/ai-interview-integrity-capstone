from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class LLMConfigError(RuntimeError):
    """Missing/invalid configuration (e.g. API key not set)."""


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient(abc.ABC):
    """Minimal text-generation interface. Implementations wrap a single provider/gateway."""

    provider: str = "base"

    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Return a single completion for ``prompt`` from ``model``."""
