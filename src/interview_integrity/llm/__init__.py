"""Provider-agnostic LLM interface (research use: controlled AI-written answers, rubric scoring).

Nothing in the data pipeline depends on this package.
"""

from .base import LLMClient, LLMConfigError, LLMResponse
from .cache import BudgetExceeded, CachedClient
from .openrouter import OpenRouterClient, OpenRouterError, load_dotenv

__all__ = ["BudgetExceeded", "CachedClient", "LLMClient", "LLMConfigError", "LLMResponse",
           "OpenRouterClient", "OpenRouterError", "load_dotenv"]
