"""Dataset registry and per-dataset acquisition adapters.

Only datasets that are publicly downloadable from their official source are
fetched automatically. Restricted datasets raise ``AccessRequired`` with the manual
steps recorded in ``manifests/datasets.json``; this code never bypasses access controls.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .manifest import FileStatus, ManifestEntry
from .remote import RemoteStorage
from .remote_zip import open_remote_zip

DEFAULT_REGISTRY = Path("manifests/datasets.json")


class AccessRequired(RuntimeError):
    """The dataset needs a manual access step (license, approval, login)."""


def load_registry(path: str | Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset registry not found: {path}")
    return json.loads(path.read_text())


def dataset_info(name: str, registry: dict[str, Any]) -> dict[str, Any]:
    try:
        return registry["datasets"][name]
    except KeyError:
        raise KeyError(f"Unknown dataset {name!r}; known: {sorted(registry['datasets'])}") from None


def require_public(name: str, info: dict[str, Any]) -> None:
    if info.get("access") != "public":
        steps = "\n".join(f"  - {s}" for s in info.get("manual_steps", []))
        raise AccessRequired(
            f"{name} cannot be downloaded automatically ({info.get('access')}).\n"
            f"Official URL: {info.get('official_source_url')}\n{steps}"
        )


# ---------------------------------------------------------------- Michigan (public)

_MICHIGAN_LABELS = {"Deceptive": "DECEPTIVE", "Truthful": "TRUTHFUL"}


def michigan_entries(info: dict[str, Any]) -> list[ManifestEntry]:
    """Build manifest rows by reading only the archive's directory (a few hundred KB)."""
    zf, _ = open_remote_zip(info["download_url"])
    members = {i.filename: i for i in zf.infolist() if not i.is_dir() and "__MACOSX" not in i.filename}

    annotation_labels: dict[str, str] = {}
    ann = next((m for m in members if m.lower().endswith(".csv") and "/annotation/" in m.lower()), None)
    if ann:
        with zf.open(ann) as fh:
            for row in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace")):
                annotation_labels[row["id"].strip()] = row["class"].strip().upper()

    entries = []
    for name, zinfo in sorted(members.items()):
        parts = PurePosixPath(name).parts
        if len(parts) < 3 or parts[-3] != "Clips" or not name.lower().endswith(".mp4"):
            continue
        folder_label = _MICHIGAN_LABELS.get(parts[-2], "UNKNOWN")
        video_file = parts[-1]
        video_id = PurePosixPath(video_file).stem
        notes = []
        ann_label = annotation_labels.get(video_file)
        if ann_label and ann_label != folder_label:
            notes.append(f"label mismatch: folder={folder_label} annotation={ann_label}")
        transcript_member = "/".join([*parts[:-3], "Transcription", parts[-2], f"{video_id}.txt"])
        if transcript_member not in members:
            transcript_member = ""
        rel = "/".join(parts[1:])  # drop the archive's top-level folder
        entries.append(ManifestEntry(
            dataset_name="michigan_deception",
            video_id=video_id,
            source_dataset=info["source_dataset"],
            official_source_url=info["official_source_url"],
            license=info["license_short"],
            participant_id="",  # speaker identity is not provided by the dataset
            deception_label=folder_label,
            drive_location=f"{info['drive_folder']}/{rel}",
            transcript_location=(
                f"{info['drive_folder']}/{'/'.join(PurePosixPath(transcript_member).parts[1:])}"
                if transcript_member else ""
            ),
            file_status=FileStatus.AVAILABLE_AT_SOURCE.value,
            archive_member=name,
            transcript_member=transcript_member,
            size_bytes=str(zinfo.file_size),
            crc32=f"{zinfo.CRC:08x}",
            notes="; ".join(notes),
        ).validate())
    return entries


@dataclass
class MirrorResult:
    uploaded: int = 0
    skipped: int = 0
    bytes_uploaded: int = 0
    bytes_fetched: int = 0


def mirror_zip_to_storage(info: dict[str, Any], entries: list[ManifestEntry], storage: RemoteStorage) -> MirrorResult:
    """Stream each listed archive member (clip + transcript) directly into storage.

    Nothing is written to local disk: bytes flow source -> memory buffer -> storage.
    ZIP CRC32 is verified while reading; stored size is verified after upload.
    Members already present with the right size are skipped, so this is resumable.
    """
    zf, raw = open_remote_zip(info["download_url"])
    sizes = {i.filename: i.file_size for i in zf.infolist()}
    result = MirrorResult()
    for e in entries:
        pairs = [(e.archive_member, e.drive_location)]
        if e.transcript_member:
            pairs.append((e.transcript_member, e.transcript_location))
        for member, remote_path in pairs:
            expected = sizes[member]
            if storage.size(remote_path) == expected:
                result.skipped += 1
                continue
            with zf.open(member) as src:  # raises BadZipFile on CRC mismatch
                written = storage.upload_stream(src, remote_path)
            if written != expected or storage.size(remote_path) != expected:
                raise IOError(f"Upload verification failed for {remote_path}")
            result.uploaded += 1
            result.bytes_uploaded += written
        e.file_status = FileStatus.IN_DRIVE.value
    result.bytes_fetched = raw.bytes_fetched
    return result


ADAPTERS = {"michigan_deception": (michigan_entries, mirror_zip_to_storage)}
