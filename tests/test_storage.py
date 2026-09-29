import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from interview_integrity.datasets.schema import SchemaError
from interview_integrity.storage.cache import CacheBudgetExceeded, TemporaryCache
from interview_integrity.storage.manifest import FileStatus, ManifestEntry, load_manifest, save_manifest
from interview_integrity.storage.remote import PROJECT_LAYOUT, LocalFolderStorage
from interview_integrity.storage.remote_zip import HttpRangeFile, remote_size
from interview_integrity.storage.sources import (
    AccessRequired,
    dataset_info,
    load_registry,
    michigan_entries,
    mirror_zip_to_storage,
    require_public,
)
from interview_integrity.storage.workflow import process_manifest_entry, processed_paths

from .conftest import requires_ffmpeg

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def storage(tmp_path) -> LocalFolderStorage:
    root = tmp_path / "AI Interview Integrity Capstone"
    root.mkdir()
    return LocalFolderStorage(root)


# ------------------------------------------------------------------ storage + layout

def test_ensure_layout_creates_and_is_idempotent(storage):
    created = storage.ensure_layout()
    assert set(created) == set(PROJECT_LAYOUT)
    (storage.root / "datasets/dolos/keep.txt").write_text("existing")
    assert storage.ensure_layout() == []
    assert (storage.root / "datasets/dolos/keep.txt").read_text() == "existing"


def test_path_traversal_rejected(storage):
    with pytest.raises(ValueError):
        storage.exists("../outside")
    with pytest.raises(ValueError):
        storage.size("/etc/passwd")


def test_upload_download_roundtrip(storage, tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello")
    storage.upload(src, "processed/x/a.txt")
    assert storage.size("processed/x/a.txt") == 5
    assert storage.upload_stream(io.BytesIO(b"abc"), "processed/x/b.txt") == 3
    assert storage.list("processed") == ["processed/x/a.txt", "processed/x/b.txt"]
    out = storage.download("processed/x/a.txt", tmp_path / "dl" / "a.txt")
    assert out.read_text() == "hello"


def test_missing_storage_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        LocalFolderStorage(tmp_path / "nope")


# ------------------------------------------------------------------ cache

def test_cache_budget_checked_before_download(storage):
    storage.upload_stream(io.BytesIO(b"x" * 2000), "datasets/big.bin")
    with TemporaryCache(max_bytes=1000) as cache:
        with pytest.raises(CacheBudgetExceeded):
            cache.fetch(storage, "datasets/big.bin")
        assert cache.used_bytes == 0


def test_cache_deleted_on_exit_even_after_error(storage, tmp_path):
    storage.upload_stream(io.BytesIO(b"data"), "datasets/f.bin")
    with pytest.raises(RuntimeError):
        with TemporaryCache(root=tmp_path / "cache") as cache:
            local = cache.fetch(storage, "datasets/f.bin")
            assert local.is_file()
            raise RuntimeError("processing failed")
    assert not local.exists()
    assert list((tmp_path / "cache").iterdir()) == []


def test_cache_fetch_missing(storage):
    with TemporaryCache() as cache, pytest.raises(FileNotFoundError):
        cache.fetch(storage, "datasets/missing.mp4")


# ------------------------------------------------------------------ manifest

def _entry(**kw):
    base = dict(dataset_name="michigan_deception", video_id="v1", source_dataset="real_life_deception",
                deception_label="DECEPTIVE", drive_location="datasets/michigan_deception/v1.mp4")
    return ManifestEntry(**{**base, **kw})


def test_manifest_roundtrip(tmp_path):
    path = tmp_path / "m.csv"
    save_manifest([_entry(), _entry(video_id="v2", deception_label="truthful")], path)
    loaded = load_manifest(path)
    assert [e.video_id for e in loaded] == ["v1", "v2"]
    assert loaded[1].deception_label == "TRUTHFUL"
    assert all(e.assistance_label == "UNKNOWN" for e in loaded)


def test_manifest_rejects_assistance_label_on_deception_dataset(tmp_path):
    with pytest.raises(SchemaError, match="deception labels only"):
        _entry(assistance_label="AI_ASSISTED").validate()


def test_manifest_rejects_unknown_columns(tmp_path):
    path = tmp_path / "m.csv"
    path.write_text("dataset_name,video_id,source_dataset,secret_column\nx,y,staged,z\n")
    with pytest.raises(SchemaError, match="unknown manifest columns"):
        load_manifest(path)


def test_committed_manifests_are_valid_and_label_safe():
    registry = load_registry(REPO / "manifests/datasets.json")
    for name, info in registry["datasets"].items():
        entries = load_manifest(REPO / "manifests/files" / f"{name}.csv")
        if info["source_dataset"] != "staged":
            assert all(e.assistance_label == "UNKNOWN" for e in entries)
    michigan = load_manifest(REPO / "manifests/files/michigan_deception.csv")
    assert len(michigan) == 121
    assert sum(e.deception_label == "DECEPTIVE" for e in michigan) == 61


def test_restricted_datasets_require_manual_access():
    registry = load_registry(REPO / "manifests/datasets.json")
    for name in ("dolos", "bag_of_lies"):
        with pytest.raises(AccessRequired, match="Official URL"):
            require_public(name, dataset_info(name, registry))
    require_public("michigan_deception", dataset_info("michigan_deception", registry))


# ------------------------------------------------------------------ remote zip + michigan adapter

@pytest.fixture
def fake_michigan_zip(tmp_path, sample_video) -> str:
    """Tiny archive mirroring the official Michigan layout, served via file:// URL."""
    top = "Real-life_Deception_Detection_2016"
    path = tmp_path / "RealLifeDeceptionDetection.2016.zip"
    ann = io.StringIO()
    w = csv.writer(ann)
    w.writerow(["id", "Smile", "class"])
    w.writerow(["trial_lie_001.mp4", "1", "deceptive"])
    w.writerow(["trial_truth_001.mp4", "0", "truthful"])
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{top}/Annotation/All_Gestures_Deceptive and Truthful.csv", ann.getvalue())
        zf.write(sample_video, f"{top}/Clips/Deceptive/trial_lie_001.mp4")
        zf.write(sample_video, f"{top}/Clips/Truthful/trial_truth_001.mp4")
        zf.writestr(f"{top}/Transcription/Deceptive/trial_lie_001.txt", "Um, I was not there. I think.")
        zf.writestr(f"{top}/Transcription/Truthful/trial_truth_001.txt", "I was at home all evening.")
    return path.resolve().as_uri()


@pytest.fixture
def michigan_info(fake_michigan_zip):
    registry = load_registry(REPO / "manifests/datasets.json")
    return {**dataset_info("michigan_deception", registry), "download_url": fake_michigan_zip}


def test_http_range_file_reads_ranges(tmp_path):
    p = tmp_path / "r.bin"
    p.write_bytes(bytes(range(256)) * 4)
    url = p.resolve().as_uri()
    assert remote_size(url) == 1024
    f = HttpRangeFile(url)
    f.seek(250)
    assert f.read(10) == bytes(range(250, 256)) + bytes(range(4))
    assert f.bytes_fetched == 10


@requires_ffmpeg
def test_michigan_entries_from_remote_archive(michigan_info):
    entries = michigan_entries(michigan_info)
    assert [(e.video_id, e.deception_label) for e in entries] == [
        ("trial_lie_001", "DECEPTIVE"), ("trial_truth_001", "TRUTHFUL")
    ]
    e = entries[0]
    assert e.assistance_label == "UNKNOWN"
    assert e.drive_location == "datasets/michigan_deception/Clips/Deceptive/trial_lie_001.mp4"
    assert e.transcript_location == "datasets/michigan_deception/Transcription/Deceptive/trial_lie_001.txt"
    assert e.participant_id == ""
    assert e.notes == ""


@requires_ffmpeg
def test_mirror_streams_members_and_is_resumable(michigan_info, storage):
    entries = michigan_entries(michigan_info)
    result = mirror_zip_to_storage(michigan_info, entries, storage)
    assert result.uploaded == 4 and result.skipped == 0
    for e in entries:
        assert storage.size(e.drive_location) == int(e.size_bytes)
        assert e.file_status == FileStatus.IN_DRIVE.value
    again = mirror_zip_to_storage(michigan_info, entries, storage)
    assert again.uploaded == 0 and again.skipped == 4


# ------------------------------------------------------------------ remote processing workflow

@requires_ffmpeg
def test_process_manifest_entry_end_to_end(michigan_info, storage, tmp_path):
    entries = michigan_entries(michigan_info)
    mirror_zip_to_storage(michigan_info, entries, storage)
    cache_root = tmp_path / "cache"

    sample = process_manifest_entry(entries[0], storage, cache_root=cache_root)

    assert sample.source_dataset.value == "real_life_deception"
    assert sample.deception_label.value == "DECEPTIVE"
    assert sample.assistance_label.value == "UNKNOWN"
    assert sample.participant_id == "unknown:trial_lie_001"
    assert sample.features["word_count"] == 7
    assert sample.video_path == entries[0].drive_location
    assert entries[0].file_status == FileStatus.PROCESSED.value
    assert entries[0].local_cache_path == ""

    paths = processed_paths(entries[0])
    for kind in ("transcript", "linguistic", "audio", "combined"):
        assert storage.exists(paths[kind]), kind
    combined = json.loads((storage.root / paths["combined"]).read_text())
    assert combined["deception_label"] == "DECEPTIVE" and combined["audio_path"] is None
    audio = json.loads((storage.root / paths["audio"]).read_text())
    assert "pause_count" in audio and "word_count" not in audio

    # Temporary local copies are gone.
    assert list(cache_root.iterdir()) == []


@requires_ffmpeg
def test_process_manifest_entry_missing_remote_file(storage):
    e = _entry(drive_location="datasets/michigan_deception/missing.mp4")
    with pytest.raises(FileNotFoundError):
        process_manifest_entry(e, storage)
    assert e.file_status == FileStatus.MISSING.value


@requires_ffmpeg
def test_process_respects_cache_budget(michigan_info, storage, tmp_path):
    entries = michigan_entries(michigan_info)
    mirror_zip_to_storage(michigan_info, entries, storage)
    with pytest.raises(CacheBudgetExceeded):
        process_manifest_entry(entries[0], storage, cache_root=tmp_path / "c", max_cache_bytes=100)
    assert list((tmp_path / "c").iterdir()) == []
