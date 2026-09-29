"""Provider-agnostic LLM interface (for generating controlled AI-assisted answers later).

Nothing in the data pipeline depends on this package.
"""

from .base import LLMClient, LLMConfigError, LLMResponse
from .openrouter import OpenRouterClient

__all__ = ["LLMClient", "LLMConfigError", "LLMResponse", "OpenRouterClient"]
