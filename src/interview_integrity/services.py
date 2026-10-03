"""Application layer: every operation the CLI offers, as reusable functions.

Functions here take plain arguments, return structured results and never print or
call ``sys.exit``, so a future API layer (framework not chosen) can call them directly.
Progress is reported through ``logging``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._fs import atomic_write_text
from .audio.extract import extract_audio
from .datasets.io import load_jsonl, upsert_jsonl, write_csv, write_jsonl
from .datasets.quality import QualityIssue, check_dataset, load_samples, summarize
from .datasets.schema import InterviewSample
from .datasets.splits import assign_splits, find_group_leakage
from .pipeline import PipelineConfig, process_video
from .storage.cache import DEFAULT_MAX_BYTES, TemporaryCache, purge_stale_caches
from .storage.manifest import FileStatus, ManifestEntry, load_manifest, save_manifest
from .storage.remote import LocalFolderStorage
from .storage.source_archive import ArchiveSourceStorage
from .storage.sources import ADAPTERS, MirrorResult, dataset_info, load_registry, require_public
from .storage.workflow import process_manifest_entry
from .transcription.base import Transcriber
from .transcription.sidecar import SidecarTranscriber

log = logging.getLogger(__name__)

VIDEO_SUFFIXES = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")


class LeakageError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- results

@dataclass
class ProcessResult:
    samples: list[InterviewSample]
    dataset_rows: int
    out_dir: Path
    issues: list[QualityIssue] = field(default_factory=list)


@dataclass
class BatchResult:
    processed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    samples: list[InterviewSample] = field(default_factory=list)
    dataset_rows: int = 0
    issues: list[QualityIssue] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed


@dataclass
class DatasetStatus:
    name: str
    access: str
    status: str
    file_counts: dict[str, int]


def _manifest_path(manifest_dir: str | Path, name: str) -> Path:
    return Path(manifest_dir) / "files" / f"{name}.csv"


def _save_outputs(samples: list[InterviewSample], out_dir: str | Path) -> int:
    out_dir = Path(out_dir)
    all_samples = upsert_jsonl(samples, out_dir / "samples.jsonl")
    write_csv(all_samples, out_dir / "samples.csv")
    return len(all_samples)


# ----------------------------------------------------------------------------- local processing

def process_local_video(
    video: str | Path,
    metadata: str | Path | dict,
    *,
    transcriber: Transcriber | None = None,
    out_dir: str | Path = "data/processed",
    config: PipelineConfig | None = None,
) -> ProcessResult:
    samples = process_video(video, metadata, transcriber=transcriber, config=config)
    rows = _save_outputs(samples, out_dir)
    return ProcessResult(samples, rows, Path(out_dir), check_dataset(samples))


def find_batch_recordings(directory: str | Path) -> list[dict[str, Path | None]]:
    """Discover ``<stem>.metadata.json`` + ``<stem>.<video>`` (+ optional ``<stem>.transcript.json|txt``)."""
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Batch directory not found: {directory}")
    found = []
    for meta in sorted(directory.glob("*.metadata.json")):
        stem = meta.name.removesuffix(".metadata.json")
        video = next((directory / f"{stem}{s}" for s in VIDEO_SUFFIXES if (directory / f"{stem}{s}").is_file()), None)
        transcript = next((directory / f"{stem}.transcript{s}" for s in (".json", ".txt")
                           if (directory / f"{stem}.transcript{s}").is_file()), None)
        found.append({"stem": stem, "metadata": meta, "video": video, "transcript": transcript})
    return found


def process_local_batch(
    directory: str | Path,
    *,
    out_dir: str | Path = "data/processed",
    config: PipelineConfig | None = None,
    transcriber: Transcriber | None = None,
) -> BatchResult:
    """Process every recording in a directory; one failure never stops the batch.

    Transcript per recording: ``<stem>.transcript.*`` if present, else ``transcriber``
    (an STT candidate) if given, else none.
    """
    result = BatchResult()
    recordings = find_batch_recordings(directory)
    if not recordings:
        raise FileNotFoundError(f"No '<name>.metadata.json' files in {directory}")
    for rec in recordings:
        stem = str(rec["stem"])
        if rec["video"] is None:
            result.failed[stem] = f"no video file named {stem}{{{','.join(VIDEO_SUFFIXES)}}}"
            continue
        tr = SidecarTranscriber(rec["transcript"]) if rec["transcript"] else transcriber
        try:
            samples = process_video(rec["video"], rec["metadata"], transcriber=tr, config=config)
        except Exception as exc:
            result.failed[stem] = f"{type(exc).__name__}: {exc}"
            log.error("%s failed: %s", stem, exc)
            continue
        result.processed.append(stem)
        result.samples.extend(samples)
        log.info("%s: %d answer(s)", stem, len(samples))
    if result.samples:
        result.dataset_rows = _save_outputs(result.samples, out_dir)
    result.issues = check_dataset(result.samples)
    report = summarize(result.issues, len(result.samples))
    report["failed_recordings"] = result.failed
    atomic_write_text(Path(out_dir) / "batch_quality_report.json", json.dumps(report, indent=2))
    return result


def assign_dataset_splits(path: str | Path, *, seed: int = 13, group_key: str = "participant_id") -> dict[str, int]:
    path = Path(path)
    samples = assign_splits(load_jsonl(path), seed=seed, group_key=group_key)
    leaks = {k: v for key in (group_key, "recording_id", "video_sha256")
             for k, v in find_group_leakage(samples, key).items()}
    if leaks:
        raise LeakageError(f"Leakage detected: {leaks}")
    write_jsonl(samples, path)
    write_csv(samples, path.with_suffix(".csv"))
    counts: dict[str, int] = {}
    for s in samples:
        counts[s.split or ""] = counts.get(s.split or "", 0) + 1
    return counts


# ----------------------------------------------------------------------------- datasets / storage

def init_storage(root: str | Path) -> list[str]:
    return LocalFolderStorage(root).ensure_layout()


def dataset_status(manifest_dir: str | Path = "manifests") -> list[DatasetStatus]:
    registry = load_registry(Path(manifest_dir) / "datasets.json")
    out = []
    for name, info in registry["datasets"].items():
        counts: dict[str, int] = {}
        path = _manifest_path(manifest_dir, name)
        if path.is_file():
            for e in load_manifest(path):
                counts[e.file_status] = counts.get(e.file_status, 0) + 1
        out.append(DatasetStatus(name, info["access"], info["status"], counts))
    return out


def build_dataset_manifest(name: str, manifest_dir: str | Path = "manifests") -> int:
    info = dataset_info(name, load_registry(Path(manifest_dir) / "datasets.json"))
    require_public(name, info)  # raises AccessRequired
    build, _ = ADAPTERS[name]
    entries = build(info)
    save_manifest(entries, _manifest_path(manifest_dir, name))
    return len(entries)


def acquire_dataset(name: str, root: str | Path, *, manifest_dir: str | Path = "manifests",
                    limit: int | None = None) -> MirrorResult:
    info = dataset_info(name, load_registry(Path(manifest_dir) / "datasets.json"))
    require_public(name, info)
    storage = LocalFolderStorage(root)
    storage.ensure_layout()
    path = _manifest_path(manifest_dir, name)
    entries = load_manifest(path)
    _, mirror = ADAPTERS[name]
    result = mirror(info, entries[:limit] if limit else entries, storage)
    save_manifest(entries, path)
    return result


def _run_entries(entries: list[ManifestEntry], todo: list[ManifestEntry], manifest: Path, run_one) -> BatchResult:
    """Process entries one by one, recording failures in the manifest instead of aborting."""
    result = BatchResult()
    try:
        for i, e in enumerate(todo, 1):
            try:
                result.samples.extend(run_one(e))
                result.processed.append(e.video_id)
                log.info("[%d/%d] %s", i, len(todo), e.video_id)
            except Exception as exc:
                e.file_status = FileStatus.ERROR.value
                e.notes = f"processing error: {exc}"[:300]
                result.failed[e.video_id] = f"{type(exc).__name__}: {exc}"
                log.error("[%d/%d] %s failed: %s", i, len(todo), e.video_id, exc)
    finally:
        save_manifest(entries, manifest)
    result.issues = check_dataset(result.samples)
    return result


def process_from_storage(
    dataset: str,
    root: str | Path,
    *,
    manifest_dir: str | Path = "manifests",
    video_ids: list[str] | None = None,
    limit: int | None = None,
    cache_dir: str | Path | None = None,
    max_cache_bytes: int = DEFAULT_MAX_BYTES,
    out_dir: str | Path = "data/processed",
    config: PipelineConfig | None = None,
) -> BatchResult:
    storage = LocalFolderStorage(root)
    path = _manifest_path(manifest_dir, dataset)
    entries = load_manifest(path)
    todo = [e for e in entries if (not video_ids or e.video_id in video_ids)
            and e.file_status in (FileStatus.IN_DRIVE.value, FileStatus.PROCESSED.value, FileStatus.ERROR.value)]
    todo = todo[:limit] if limit else todo
    result = _run_entries(entries, todo, path, lambda e: process_manifest_entry(
        e, storage, cache_root=cache_dir, max_cache_bytes=max_cache_bytes, config=config))
    if result.samples:
        result.dataset_rows = _save_outputs(result.samples, out_dir)
    return result


def _collect_combined_csv(out: LocalFolderStorage, dataset: str) -> int:
    prefix = f"processed/combined_features/{dataset}"
    rows = [json.loads((out.root / p).read_text()) for p in out.list(prefix) if p.endswith(".json")]
    write_csv([InterviewSample.from_row(r) for r in rows], out.root / f"{prefix}.csv")
    return len(rows)


def process_from_source(
    dataset: str,
    *,
    manifest_dir: str | Path = "manifests",
    out_root: str | Path = ".",
    video_ids: list[str] | None = None,
    limit: int | None = None,
    force: bool = False,
    cache_dir: str | Path | None = None,
    max_cache_bytes: int = DEFAULT_MAX_BYTES,
) -> BatchResult:
    info = dataset_info(dataset, load_registry(Path(manifest_dir) / "datasets.json"))
    require_public(dataset, info)
    path = _manifest_path(manifest_dir, dataset)
    entries = load_manifest(path)
    source = ArchiveSourceStorage.from_manifest(info["download_url"], entries)
    out = LocalFolderStorage(out_root)
    todo = [e for e in entries if not video_ids or e.video_id in video_ids]
    if not force:
        skip = [e for e in todo if out.exists(f"processed/combined_features/{e.dataset_name}/{e.video_id}.json")]
        todo = [e for e in todo if e not in skip]
    todo = todo[:limit] if limit else todo
    try:
        result = _run_entries(entries, todo, path, lambda e: process_manifest_entry(
            e, source, output_storage=out, cache_root=cache_dir, max_cache_bytes=max_cache_bytes))
    finally:
        rows = _collect_combined_csv(out, dataset)
    result.dataset_rows = rows
    result.extra["mb_fetched_from_source"] = round(source.bytes_fetched / 2**20, 1)
    return result


# ----------------------------------------------------------------------------- quality / STT

def run_quality(input_path: str | Path, report_path: str | Path | None = None) -> dict[str, Any]:
    samples = load_samples(input_path)
    report = summarize(check_dataset(samples), len(samples))
    if report_path:
        atomic_write_text(report_path, json.dumps(report, indent=2))
    return report


def evaluate_stt(reference_dir: str | Path, hypothesis_dir: str | Path,
                 report_path: str | Path | None = None) -> dict[str, Any]:
    from .transcription.evaluate import evaluate_directories

    report = evaluate_directories(reference_dir, hypothesis_dir)
    if report_path:
        atomic_write_text(report_path, json.dumps(report, indent=2))
    return report


def _benchmark_clips_from_dirs(audio_dir: Path, reference_dir: Path, cache: TemporaryCache, limit: int | None):
    from .transcription.benchmark import Clip

    refs = {p.stem.removesuffix(".transcript"): p for p in reference_dir.iterdir() if p.suffix in (".txt", ".json")}
    media = sorted(p for p in audio_dir.iterdir() if p.suffix in (".wav", *VIDEO_SUFFIXES) and p.stem in refs)
    clips = []
    for p in media[:limit] if limit else media:
        info = extract_audio(p, cache.path(f"{p.stem}.wav"))
        clips.append(Clip(p.stem, Path(info.path), SidecarTranscriber(refs[p.stem]).transcribe(), info.duration or 0.0))
    return clips


def _benchmark_clips_from_source(dataset: str, manifest_dir: Path, cache: TemporaryCache, limit: int | None):
    from .transcription.benchmark import Clip

    info = dataset_info(dataset, load_registry(manifest_dir / "datasets.json"))
    require_public(dataset, info)
    entries = [e for e in load_manifest(_manifest_path(manifest_dir, dataset)) if e.transcript_location]
    entries = entries[:limit] if limit else entries
    source = ArchiveSourceStorage.from_manifest(info["download_url"], entries)
    clips = []
    for e in entries:
        video = cache.fetch(source, e.drive_location)
        audio = extract_audio(video, cache.path(f"{e.video_id}.wav"))
        video.unlink()  # keep only the small WAV while benchmarking
        ref = SidecarTranscriber(cache.fetch(source, e.transcript_location)).transcribe()
        clips.append(Clip(e.video_id, Path(audio.path), ref, audio.duration or 0.0))
    return clips


def run_stt_benchmark(
    candidates_path: str | Path,
    *,
    dataset: str | None = None,
    audio_dir: str | Path | None = None,
    reference_dir: str | Path | None = None,
    manifest_dir: str | Path = "manifests",
    limit: int | None = 20,
    allow_external_upload: bool = False,
    cache_dir: str | Path | None = None,
    max_cache_bytes: int = DEFAULT_MAX_BYTES,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Benchmark STT candidates on a public dataset (streamed) or local audio+reference dirs."""
    from .transcription.benchmark import load_candidates, run_benchmark
    from .transcription.registry import create_transcriber

    if (dataset is None) == (audio_dir is None):
        raise ValueError("Give either dataset or audio_dir (+ reference_dir)")
    candidates = load_candidates(candidates_path)
    with TemporaryCache(cache_dir, max_cache_bytes) as cache:
        if dataset:
            clips = _benchmark_clips_from_source(dataset, Path(manifest_dir), cache, limit)
        else:
            if reference_dir is None:
                raise ValueError("reference_dir is required with audio_dir")
            clips = _benchmark_clips_from_dirs(Path(audio_dir), Path(reference_dir), cache, limit)
        report = run_benchmark(candidates, clips, create_transcriber, allow_external_upload=allow_external_upload)
    if report_path:
        atomic_write_text(report_path, json.dumps(report, indent=2))
    return report


# ----------------------------------------------------------------------------- staged / housekeeping

def staged_template(interview_id: str, participant_id: str, question_bank: str | Path,
                    conditions: dict[str, str] | None = None, out_path: str | Path | None = None) -> dict:
    from .staged import load_question_bank, make_template

    template = make_template(interview_id, participant_id, load_question_bank(question_bank), conditions)
    if out_path:
        if Path(out_path).exists():
            raise FileExistsError(f"{out_path} already exists; refusing to overwrite")
        atomic_write_text(out_path, json.dumps(template, indent=2) + "\n")
    return template


def staged_import_labels(metadata_path: str | Path, labels_path: str | Path,
                         out_path: str | Path | None = None) -> dict:
    from .staged import apply_labels, read_labels

    updated = apply_labels(json.loads(Path(metadata_path).read_text()), read_labels(labels_path))
    atomic_write_text(out_path or metadata_path, json.dumps(updated, indent=2) + "\n")
    return updated


def staged_validate(metadata_path: str | Path):
    from .staged import validate_staged

    return validate_staged(json.loads(Path(metadata_path).read_text()))


def clean_caches(root: str | Path | None = None, older_than_hours: float = 12.0) -> list[Path]:
    return purge_stale_caches(root, older_than_hours)
