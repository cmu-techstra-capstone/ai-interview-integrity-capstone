"""Size-bounded temporary local cache that is always deleted on exit."""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

from .remote import RemoteStorage

DEFAULT_MAX_BYTES = 500 * 1024 * 1024  # team rule: never exceed 500 MB locally without asking
CACHE_PREFIX = "iic-cache-"

log = logging.getLogger(__name__)


class CacheBudgetExceeded(RuntimeError):
    pass


class TemporaryCache:
    """Context manager for a scratch directory with a hard byte budget.

    ``fetch`` checks the remote size *before* downloading and refuses anything that
    would push total usage over ``max_bytes``. The directory is removed on exit,
    including when processing fails.
    """

    def __init__(self, root: str | Path | None = None, max_bytes: int = DEFAULT_MAX_BYTES):
        self.root = Path(root) if root else None
        self.max_bytes = max_bytes
        self.dir: Path | None = None

    def __enter__(self) -> "TemporaryCache":
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
        self.dir = Path(tempfile.mkdtemp(prefix=CACHE_PREFIX, dir=self.root))
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self.dir and self.dir.exists():
            shutil.rmtree(self.dir)
        self.dir = None

    def _require_open(self) -> Path:
        if self.dir is None:
            raise RuntimeError("TemporaryCache is not open; use it as a context manager")
        return self.dir

    @property
    def used_bytes(self) -> int:
        d = self._require_open()
        return sum(p.stat().st_size for p in d.rglob("*") if p.is_file())

    def reserve(self, nbytes: int) -> None:
        if self.used_bytes + nbytes > self.max_bytes:
            raise CacheBudgetExceeded(
                f"Need {nbytes / 2**20:.1f} MB but cache budget allows "
                f"{(self.max_bytes - self.used_bytes) / 2**20:.1f} MB more (limit {self.max_bytes / 2**20:.0f} MB)"
            )

    def path(self, name: str) -> Path:
        return self._require_open() / name

    def fetch(self, storage: RemoteStorage, remote_path: str, name: str | None = None) -> Path:
        size = storage.size(remote_path)
        if size is None:
            raise FileNotFoundError(f"Remote file not found: {remote_path}")
        self.reserve(size)
        local = self.path(name or Path(remote_path).name)
        storage.download(remote_path, local)
        if local.stat().st_size != size:
            raise IOError(f"Size mismatch downloading {remote_path}: {local.stat().st_size} != {size}")
        return local


def purge_stale_caches(root: str | Path | None = None, older_than_hours: float = 12.0) -> list[Path]:
    """Delete leftover cache dirs (e.g. from a killed process) older than ``older_than_hours``.

    Only directories named ``iic-cache-*`` directly under ``root`` (default: system temp dir)
    are touched; nothing else is ever removed.
    """
    base = Path(root) if root else Path(tempfile.gettempdir())
    if not base.is_dir():
        return []
    cutoff = time.time() - older_than_hours * 3600
    removed = []
    for d in base.iterdir():
        if d.is_dir() and not d.is_symlink() and d.name.startswith(CACHE_PREFIX) and d.stat().st_mtime < cutoff:
            shutil.rmtree(d)
            removed.append(d)
            log.info("removed stale cache %s", d)
    return removed
