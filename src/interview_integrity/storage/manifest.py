"""File-level dataset manifest: where every raw file lives, without copying it into Git.

One CSV per dataset under ``manifests/files/<dataset_name>.csv``. ``drive_location``
is relative to the shared project root folder ("AI Interview Integrity Capstone/").
"""

from __future__ import annotations

import csv
import enum
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Iterable

from ..datasets.schema import (
    AssistanceLabel,
    DeceptionLabel,
    SchemaError,
    SourceDataset,
    _check_label_separation,
    _parse_enum,
)


class FileStatus(str, enum.Enum):
    AVAILABLE_AT_SOURCE = "AVAILABLE_AT_SOURCE"  # public, not yet copied to shared storage
    ACCESS_PENDING = "ACCESS_PENDING"  # needs license/approval before it can be obtained
    IN_DRIVE = "IN_DRIVE"  # raw file present in shared storage
    PROCESSED = "PROCESSED"  # processed outputs uploaded to shared storage
    MISSING = "MISSING"  # expected but not found
    ERROR = "ERROR"


@dataclass
class ManifestEntry:
    dataset_name: str
    video_id: str
    source_dataset: str
    official_source_url: str = ""
    license: str = ""
    participant_id: str = ""
    question_id: str = ""
    deception_label: str = DeceptionLabel.UNKNOWN.value
    assistance_label: str = AssistanceLabel.UNKNOWN.value
    drive_location: str = ""
    transcript_location: str = ""
    remote_reference: str = ""  # backend-specific ID (e.g. Drive file ID), if any
    file_status: str = FileStatus.AVAILABLE_AT_SOURCE.value
    local_cache_path: str = ""  # only set while a file is temporarily cached
    archive_member: str = ""
    transcript_member: str = ""
    size_bytes: str = ""
    crc32: str = ""
    notes: str = ""

    def validate(self) -> "ManifestEntry":
        where = f"{self.dataset_name}/{self.video_id}"
        if not self.dataset_name or not self.video_id:
            raise SchemaError(f"{where}: dataset_name and video_id are required")
        source = _parse_enum(SourceDataset, self.source_dataset, "source_dataset")
        assistance = _parse_enum(AssistanceLabel, self.assistance_label, "assistance_label", AssistanceLabel.UNKNOWN)
        deception = _parse_enum(DeceptionLabel, self.deception_label, "deception_label", DeceptionLabel.UNKNOWN)
        _check_label_separation(source, assistance, where)
        status = _parse_enum(FileStatus, self.file_status, "file_status", FileStatus.AVAILABLE_AT_SOURCE)
        self.source_dataset, self.assistance_label = source.value, assistance.value
        self.deception_label, self.file_status = deception.value, status.value
        return self


COLUMNS = tuple(f.name for f in fields(ManifestEntry))


def load_manifest(path: str | Path) -> list[ManifestEntry]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Manifest not found: {path}")
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        unknown = set(reader.fieldnames or []) - set(COLUMNS)
        if unknown:
            raise SchemaError(f"{path}: unknown manifest columns {sorted(unknown)}")
        return [ManifestEntry(**{k: v or "" for k, v in row.items()}).validate() for row in reader]


def save_manifest(entries: Iterable[ManifestEntry], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for e in entries:
            writer.writerow(asdict(e.validate()))
