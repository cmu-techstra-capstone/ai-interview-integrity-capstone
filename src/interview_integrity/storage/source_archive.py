"""Read-only storage backed directly by a dataset's official ZIP archive.

Serves individual archive members on demand via HTTP range requests, so a single
clip can be pulled from the official source into the temp cache without the dataset
being stored anywhere else (no Drive, no local copy of the archive).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO, Iterable

from .manifest import ManifestEntry
from .remote import RemoteStorage, _clean
from .remote_zip import open_remote_zip


class ReadOnlyStorageError(RuntimeError):
    pass


class ArchiveSourceStorage(RemoteStorage):
    name = "source_archive"

    def __init__(self, url: str, path_to_member: dict[str, str]):
        self.url = url
        self.path_to_member = {_clean(k): v for k, v in path_to_member.items()}
        self._zip = None
        self._raw = None

    @classmethod
    def from_manifest(cls, url: str, entries: Iterable[ManifestEntry]) -> "ArchiveSourceStorage":
        mapping: dict[str, str] = {}
        for e in entries:
            if e.drive_location and e.archive_member:
                mapping[e.drive_location] = e.archive_member
            if e.transcript_location and e.transcript_member:
                mapping[e.transcript_location] = e.transcript_member
        return cls(url, mapping)

    @property
    def bytes_fetched(self) -> int:
        return self._raw.bytes_fetched if self._raw else 0

    def _zipfile(self):
        if self._zip is None:
            self._zip, self._raw = open_remote_zip(self.url)
        return self._zip

    def _member(self, remote_path: str) -> str | None:
        return self.path_to_member.get(_clean(remote_path))

    def exists(self, remote_path: str) -> bool:
        member = self._member(remote_path)
        return member is not None and member in self._zipfile().NameToInfo

    def size(self, remote_path: str) -> int | None:
        member = self._member(remote_path)
        if member is None:
            return None
        info = self._zipfile().NameToInfo.get(member)
        return info.file_size if info else None

    def download(self, remote_path: str, local_path: Path) -> Path:
        member = self._member(remote_path)
        if member is None or not self.exists(remote_path):
            raise FileNotFoundError(f"Not in source archive: {remote_path}")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with self._zipfile().open(member) as src, open(local_path, "wb") as dst:  # CRC verified on read
            shutil.copyfileobj(src, dst, length=1 << 20)
        return local_path

    def reference(self, remote_path: str) -> str:
        return f"{self.url}#{self._member(remote_path) or remote_path}"

    def list(self, prefix: str = "") -> list[str]:
        return sorted(p for p in self.path_to_member if p.startswith(prefix))

    def upload(self, local_path: Path, remote_path: str) -> None:
        raise ReadOnlyStorageError("The official source archive is read-only")

    def upload_stream(self, stream: BinaryIO, remote_path: str) -> int:
        raise ReadOnlyStorageError("The official source archive is read-only")

    def mkdirs(self, remote_path: str) -> None:
        raise ReadOnlyStorageError("The official source archive is read-only")
