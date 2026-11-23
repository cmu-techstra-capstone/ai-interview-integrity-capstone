"""Remote dataset storage: manifests, storage backends, bounded local cache, acquisition.

Design: Google Drive (or any shared store) holds raw datasets; GitHub holds code and
manifests; the laptop only ever holds a small, size-bounded temporary cache.
"""

from .cache import CacheBudgetExceeded, TemporaryCache
from .manifest import FileStatus, ManifestEntry, load_manifest, save_manifest
from .remote import LocalFolderStorage, RemoteStorage

__all__ = [
    "CacheBudgetExceeded",
    "TemporaryCache",
    "FileStatus",
    "ManifestEntry",
    "load_manifest",
    "save_manifest",
    "LocalFolderStorage",
    "RemoteStorage",
]
