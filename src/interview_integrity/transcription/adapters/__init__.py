"""Optional speech-to-text adapters.

``faster-whisper`` small / CPU / INT8 is the approved *optional* offline baseline when
explicitly selected; it is not auto-applied. WhisperX and hosted remain unevaluated /
blocked. Each adapter imports its third-party library lazily, so the core package never
depends on heavy ML packages. Install only on a machine with enough disk
(see docs/teammate-validation.md), e.g. ``pip install -e ".[stt-faster-whisper]"``.
"""

from .base import MissingOptionalDependency, ModelNotAvailable

__all__ = ["MissingOptionalDependency", "ModelNotAvailable"]
