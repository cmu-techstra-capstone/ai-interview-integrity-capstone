"""Optional speech-to-text adapters (candidates under evaluation; none is the project default).

Each adapter imports its third-party library lazily, so the core package never depends
on heavy ML packages. Install a candidate only on a machine with enough disk
(see docs/teammate-validation.md), e.g. ``pip install -e ".[stt-faster-whisper]"``.
"""

from .base import MissingOptionalDependency, ModelNotAvailable

__all__ = ["MissingOptionalDependency", "ModelNotAvailable"]
