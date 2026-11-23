"""Safe resolution of relative recording paths under an authorized root."""

from __future__ import annotations

import os
from pathlib import Path

from .config import ApiSettings


class PathValidationError(ValueError):
    """Client-safe path rejection (message must not leak absolute paths)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def validate_relative_input(relpath: str, *, field: str) -> str:
    """Reject absolute paths, empty values, and ``..`` segments before joining."""
    if not isinstance(relpath, str) or not relpath.strip():
        raise PathValidationError("invalid_path", f"{field} is required")
    cleaned = relpath.strip().replace("\\", "/")
    if cleaned.startswith("/") or cleaned.startswith("~") or (len(cleaned) > 1 and cleaned[1] == ":"):
        raise PathValidationError("invalid_path", f"{field} must be a relative path under the authorized recordings directory")
    parts = Path(cleaned).parts
    if any(p in {"..", ""} for p in parts):
        raise PathValidationError("invalid_path", f"{field} must not contain '..' or empty segments")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def resolve_authorized_file(
    settings: ApiSettings,
    relpath: str,
    *,
    field: str,
    allowed_suffixes: tuple[str, ...] | None = None,
    must_exist: bool = True,
) -> Path:
    """Resolve ``relpath`` under ``settings.recordings_dir`` without escaping the root.

    Uses ``os.path.realpath`` so symlink escapes outside the root are rejected.
    """
    rel = validate_relative_input(relpath, field=field)
    root = Path(os.path.realpath(settings.recordings_dir))
    if not root.is_dir():
        raise PathValidationError(
            "recordings_dir_missing",
            "Authorized recordings directory is not configured or does not exist on the server",
        )

    joined = root / rel
    # Disallow following a symlink that points outside root.
    real = Path(os.path.realpath(joined))
    if not _is_within(root, real):
        raise PathValidationError(
            "path_outside_root",
            f"{field} resolves outside the authorized recordings directory",
        )

    if must_exist and not real.is_file():
        raise PathValidationError("file_not_found", f"{field} was not found in the authorized recordings directory")

    if allowed_suffixes is not None and real.suffix.lower() not in {s.lower() for s in allowed_suffixes}:
        raise PathValidationError(
            "unsupported_file",
            f"{field} has an unsupported file type",
        )
    return real
