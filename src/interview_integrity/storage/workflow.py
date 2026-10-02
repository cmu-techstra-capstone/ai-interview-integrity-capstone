"""Process one manifest entry: storage -> bounded temp cache -> features -> output storage.

    raw video (+ transcript, + recording metadata) from ``storage`` -> TemporaryCache
      -> process_video -> transcript + feature JSON written to ``output_storage``
      under processed/ -> cache deleted

``storage`` can be shared Drive storage or the official source archive itself
(``ArchiveSourceStorage``); ``output_storage`` defaults to ``storage``.

Recording metadata comes from ``entry.metadata_location`` (a JSON file in storage,
used for staged interviews with several questions and AI-generation metadata) or,
if absent, is derived from the manifest row (one answer per clip, as in public datasets).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..datasets.schema import CORE_COLUMNS, InterviewSample, RecordingMetadata, SchemaError
from ..features.linguistic import extract_linguistic_features
from ..pipeline import PipelineConfig, process_video
from ..transcription.sidecar import SidecarTranscriber
from .cache import DEFAULT_MAX_BYTES, TemporaryCache
from .manifest import FileStatus, ManifestEntry
from .remote import RemoteStorage

LINGUISTIC_KEYS = frozenset(extract_linguistic_features("x")) | {"transcript_source"}
ID_KEYS = ("interview_id", "participant_id", "question_id", "recording_id", "source_dataset",
           "assistance_label", "deception_label")
TIMING_CORE_KEYS = ("question_start", "question_end", "answer_start", "answer_end",
                    "answer_duration", "response_latency")


def processed_paths(entry: ManifestEntry, question_id: str | None = None) -> dict[str, str]:
    """Output locations. Single-answer recordings keep ``<video_id>.json``; multi-answer
    recordings get one file per question: ``<video_id>__<question_id>.json``."""
    name = entry.video_id if question_id is None else f"{entry.video_id}__{question_id}"
    stem = f"{entry.dataset_name}/{name}"
    return {
        "transcript": f"processed/transcripts/{entry.dataset_name}/{entry.video_id}.json",
        "linguistic": f"processed/linguistic_features/{stem}.json",
        "audio": f"processed/audio_features/{stem}.json",
        "combined": f"processed/combined_features/{stem}.json",
    }


def _metadata_from_entry(entry: ManifestEntry) -> dict:
    return {
        "interview_id": entry.video_id,
        "participant_id": entry.participant_id or f"unknown:{entry.video_id}",
        "source_dataset": entry.source_dataset,
        "question_id": entry.question_id or "Q_NA",
        "assistance_label": entry.assistance_label,
        "deception_label": entry.deception_label,
    }


def _load_metadata(entry: ManifestEntry, path: Path) -> RecordingMetadata:
    meta = RecordingMetadata.from_json(path)
    if meta.source_dataset.value != entry.source_dataset:
        raise SchemaError(
            f"{entry.video_id}: metadata source_dataset {meta.source_dataset.value!r} "
            f"does not match manifest {entry.source_dataset!r}"
        )
    if entry.participant_id and meta.participant_id != entry.participant_id:
        raise SchemaError(
            f"{entry.video_id}: metadata participant_id {meta.participant_id!r} "
            f"does not match manifest {entry.participant_id!r}"
        )
    return meta


def split_row(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a combined row into linguistic and audio/timing subsets (both keep the IDs)."""
    ids = {k: row[k] for k in ID_KEYS}
    features = {k: v for k, v in row.items() if k not in CORE_COLUMNS}
    linguistic = {**ids, **{k: v for k, v in features.items() if k in LINGUISTIC_KEYS}}
    audio = {
        **ids,
        **{k: row[k] for k in TIMING_CORE_KEYS},
        **{k: v for k, v in features.items() if k not in LINGUISTIC_KEYS},
    }
    return linguistic, audio


def process_manifest_entry(
    entry: ManifestEntry,
    storage: RemoteStorage,
    *,
    output_storage: RemoteStorage | None = None,
    cache_root: str | Path | None = None,
    max_cache_bytes: int = DEFAULT_MAX_BYTES,
    config: PipelineConfig | None = None,
) -> list[InterviewSample]:
    """Process one recording; returns one sample per answer."""
    output_storage = output_storage or storage
    if not storage.exists(entry.drive_location):
        entry.file_status = FileStatus.MISSING.value
        raise FileNotFoundError(f"{entry.video_id}: raw file not in shared storage: {entry.drive_location}")

    samples: list[InterviewSample] = []
    with TemporaryCache(cache_root, max_cache_bytes) as cache:
        video = cache.fetch(storage, entry.drive_location)
        transcriber = None
        if entry.transcript_location and storage.exists(entry.transcript_location):
            transcriber = SidecarTranscriber(cache.fetch(storage, entry.transcript_location))
        if entry.metadata_location:
            if not storage.exists(entry.metadata_location):
                raise FileNotFoundError(f"{entry.video_id}: metadata not in storage: {entry.metadata_location}")
            metadata: Any = _load_metadata(entry, cache.fetch(storage, entry.metadata_location, "metadata.json"))
        else:
            metadata = _metadata_from_entry(entry)
        entry.local_cache_path = str(video)

        run_config = config or PipelineConfig()
        run_config = PipelineConfig(**{**run_config.__dict__, "interim_dir": cache.path("interim")})
        processed = process_video(video, metadata, transcriber=transcriber, config=run_config)
        multi = len(processed) > 1

        for sample in processed:
            row = sample.to_row()
            # Local cache paths are meaningless once the cache is gone; point at the source instead.
            row.update(video_reference=storage.reference(entry.drive_location), audio_reference=None)
            paths = processed_paths(entry, sample.question_id if multi else None)
            row["transcript_path"] = paths["transcript"] if transcriber else None

            outputs = {"combined": row}
            outputs["linguistic"], outputs["audio"] = split_row(row)
            for kind, payload in outputs.items():
                out = cache.path(f"{kind}.json")
                out.write_text(json.dumps(payload, indent=2))
                output_storage.upload(out, paths[kind])
            samples.append(InterviewSample.from_row(row))

        if processed and processed[0].transcript_path:
            output_storage.upload(Path(processed[0].transcript_path), processed_paths(entry)["transcript"])

    entry.local_cache_path = ""
    entry.file_status = FileStatus.PROCESSED.value
    return samples
