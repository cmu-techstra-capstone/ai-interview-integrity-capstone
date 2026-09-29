"""Read members of a remote ZIP archive via HTTP range requests.

Lets us list an archive and stream individual members straight into shared storage
without downloading the whole archive to local disk. Uses the ``curl`` binary for
transport because it validates TLS against the OS trust store (some university
servers omit intermediate certificates, which Python's bundled verification rejects).
"""

from __future__ import annotations

import io
import shutil
import subprocess
import zipfile


class RangeRequestError(RuntimeError):
    pass


def _curl() -> str:
    path = shutil.which("curl")
    if path is None:
        raise RangeRequestError("curl is required for remote archive access")
    return path


def remote_size(url: str) -> int:
    """Content length via a HEAD request (no body downloaded)."""
    result = subprocess.run(
        [_curl(), "-sfIL", url], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RangeRequestError(f"HEAD request failed for {url} (curl exit {result.returncode})")
    lengths = [
        int(line.split(":", 1)[1]) for line in result.stdout.splitlines()
        if line.lower().startswith("content-length:")
    ]
    if not lengths:
        raise RangeRequestError(f"Server did not report a size for {url}")
    return lengths[-1]


class HttpRangeFile(io.RawIOBase):
    """Seekable read-only file object backed by HTTP range requests."""

    def __init__(self, url: str, size: int | None = None):
        self.url = url
        self.size = size if size is not None else remote_size(url)
        self.pos = 0
        self.bytes_fetched = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = base + offset
        return self.pos

    def readinto(self, buffer) -> int:
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(buffer), self.size) - 1
        result = subprocess.run(
            [_curl(), "-sf", "-r", f"{self.pos}-{end}", self.url], capture_output=True
        )
        if result.returncode != 0:
            raise RangeRequestError(f"Range request {self.pos}-{end} failed for {self.url}")
        data = result.stdout
        expected = end - self.pos + 1
        if len(data) != expected:
            raise RangeRequestError(
                f"Server returned {len(data)} bytes for a {expected}-byte range; range requests unsupported?"
            )
        buffer[: len(data)] = data
        self.pos += len(data)
        self.bytes_fetched += len(data)
        return len(data)


def open_remote_zip(url: str, buffer_size: int = 1 << 20) -> tuple[zipfile.ZipFile, HttpRangeFile]:
    raw = HttpRangeFile(url)
    return zipfile.ZipFile(io.BufferedReader(raw, buffer_size=buffer_size)), raw
