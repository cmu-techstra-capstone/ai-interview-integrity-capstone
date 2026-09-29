"""Storage backend interface.

Remote paths are POSIX-style and relative to the project's shared root folder
(``AI Interview Integrity Capstone/``), e.g. ``datasets/michigan_deception/clip.mp4``.

Only ``LocalFolderStorage`` is implemented. It works for any mounted folder, including
a Google Drive for Desktop mount. A Drive-API or rclone backend is a pending
decision (docs/decisions.md, D6) and should implement ``RemoteStorage``.
"""

from __future__ import annotations

import abc
import shutil
from pathlib import Path, PurePosixPath
from typing import BinaryIO

# Folder layout of the shared project root. Created without touching existing content.
PROJECT_LAYOUT: tuple[str, ...] = (
    "datasets/dolos",
    "datasets/michigan_deception",
    "datasets/bag_of_lies",
    "datasets/staged_interviews",
    "processed/transcripts",
    "processed/audio_features",
    "processed/linguistic_features",
    "processed/combined_features",
    "metadata",
    "docs",
)


def _clean(remote_path: str) -> str:
    p = PurePosixPath(remote_path)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"Remote paths must be relative and inside the project root: {remote_path!r}")
    return str(p)


class RemoteStorage(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def exists(self, remote_path: str) -> bool: ...

    @abc.abstractmethod
    def size(self, remote_path: str) -> int | None:
        """Size in bytes, or ``None`` if the file does not exist."""

    @abc.abstractmethod
    def download(self, remote_path: str, local_path: Path) -> Path: ...

    @abc.abstractmethod
    def upload(self, local_path: Path, remote_path: str) -> None: ...

    @abc.abstractmethod
    def upload_stream(self, stream: BinaryIO, remote_path: str) -> int:
        """Write a stream to ``remote_path`` without a local temp file. Returns bytes written."""

    @abc.abstractmethod
    def mkdirs(self, remote_path: str) -> None: ...

    @abc.abstractmethod
    def list(self, prefix: str = "") -> list[str]:
        """Recursively list file paths under ``prefix``."""

    def ensure_layout(self, layout: tuple[str, ...] = PROJECT_LAYOUT) -> list[str]:
        """Create missing project folders. Never deletes or overwrites. Returns folders created."""
        created = []
        for folder in layout:
            if not self.exists(folder):
                self.mkdirs(folder)
                created.append(folder)
        return created


class LocalFolderStorage(RemoteStorage):
    """A directory on disk acting as the shared root (e.g. a Drive for Desktop mount)."""

    name = "local_folder"

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        if not self.root.is_dir():
            raise FileNotFoundError(f"Storage root does not exist: {self.root}")

    def _p(self, remote_path: str) -> Path:
        return self.root / _clean(remote_path)

    def exists(self, remote_path: str) -> bool:
        return self._p(remote_path).exists()

    def size(self, remote_path: str) -> int | None:
        p = self._p(remote_path)
        return p.stat().st_size if p.is_file() else None

    def download(self, remote_path: str, local_path: Path) -> Path:
        src = self._p(remote_path)
        if not src.is_file():
            raise FileNotFoundError(f"Remote file not found: {remote_path}")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, local_path)
        return local_path

    def upload(self, local_path: Path, remote_path: str) -> None:
        dst = self._p(remote_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, dst)

    def upload_stream(self, stream: BinaryIO, remote_path: str) -> int:
        dst = self._p(remote_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".partial")
        with open(tmp, "wb") as fh:
            shutil.copyfileobj(stream, fh, length=1 << 20)
        tmp.replace(dst)
        return dst.stat().st_size

    def mkdirs(self, remote_path: str) -> None:
        self._p(remote_path).mkdir(parents=True, exist_ok=True)

    def list(self, prefix: str = "") -> list[str]:
        base = self._p(prefix) if prefix else self.root
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root).as_posix()) for p in base.rglob("*") if p.is_file())
