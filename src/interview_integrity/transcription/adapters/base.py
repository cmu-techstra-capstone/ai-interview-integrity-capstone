from __future__ import annotations

import importlib
from types import ModuleType


class MissingOptionalDependency(ImportError):
    """An optional STT package is not installed."""


class ModelNotAvailable(RuntimeError):
    """Model weights are not present locally and downloading was not allowed."""


class ExternalUploadNotApproved(PermissionError):
    """A hosted STT service would receive audio, but that has not been approved."""


def import_optional(module: str, extra: str) -> ModuleType:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise MissingOptionalDependency(
            f"'{module}' is not installed. On a machine with enough disk run: pip install -e '.[{extra}]'"
        ) from exc
