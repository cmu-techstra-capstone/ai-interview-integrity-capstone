"""Process one manifest entry: shared storage -> bounded temp cache -> features -> shared storage.

    remote raw video (+ transcript) -> TemporaryCache -> process_video
      -> upload transcript + feature JSON to processed/ -> cache deleted
"""

from __future__ import annotations

import json
from pathlib import Path

from ..datasets.schema import InterviewSample
from ..features.linguistic import extract_linguistic_features
from ..pipeline import PipelineConfig, process_video
from ..transcription.sidecar import SidecarTranscriber
from .cache import DEFAULT_MAX_BYTES, TemporaryCache
from .manifest import FileStatus, ManifestEntry
from .remote import RemoteStorage

LINGUISTIC_KEYS = frozenset(extract_linguistic_features("x"))
ID_KEYS = ("interview_id", "participant_id", "question_id", "recording_id", "source_dataset",
           "assistance_label", "deception_label")


def processed_paths(entry: ManifestEntry) -> dict[str, str]:
    stem = f"{entry.dataset_name}/{entry.video_id}"
    return {
        "transcript": f"processed/transcripts/{stem}.json",
        "linguistic": f"processed/linguistic_features/{stem}.json",
        "audio": f"processed/audio_features/{stem}.json",
        "combined": f"processed/combined_features/{stem}.json",
    }


def _to_metadata(entry: ManifestEntry) -> dict:
    return {
        "interview_id": entry.video_id,
        "participant_id": entry.participant_id or f"unknown:{entry.video_id}",
        "source_dataset": entry.source_dataset,
        "question_id": entry.question_id or "Q_NA",
        "assistance_label": entry.assistance_label,
        "deception_label": entry.deception_label,
    }


def _split_row(row: dict) -> tuple[dict, dict]:
    ids = {k: row[k] for k in ID_KEYS}
    linguistic = {**ids, **{k: v for k, v in row.items() if k in LINGUISTIC_KEYS}}
    audio_keys = {"answer_start", "answer_end", "answer_duration", "response_latency", "timing_source",
                  "speech_duration", "pause_count", "mean_pause_duration", "max_pause_duration",
                  "total_pause_duration", "pause_ratio", "speech_rate_wpm", "articulation_rate_wpm"}
    audio = {**ids, **{k: v for k, v in row.items() if k in audio_keys}}
    return linguistic, audio


def process_manifest_entry(
    entry: ManifestEntry,
    storage: RemoteStorage,
    *,
    cache_root: str | Path | None = None,
    max_cache_bytes: int = DEFAULT_MAX_BYTES,
) -> InterviewSample:
    if not storage.exists(entry.drive_location):
        entry.file_status = FileStatus.MISSING.value
        raise FileNotFoundError(f"{entry.video_id}: raw file not in shared storage: {entry.drive_location}")

    with TemporaryCache(cache_root, max_cache_bytes) as cache:
        video = cache.fetch(storage, entry.drive_location)
        transcriber = None
        if entry.transcript_location and storage.exists(entry.transcript_location):
            transcriber = SidecarTranscriber(cache.fetch(storage, entry.transcript_location))
        entry.local_cache_path = str(video)

        [sample] = process_video(
            video,
            _to_metadata(entry),
            transcriber=transcriber,
            config=PipelineConfig(interim_dir=cache.path("interim")),
        )
        row = sample.to_row()
        # Local cache paths are meaningless once the cache is gone; point at shared storage instead.
        row.update(video_path=entry.drive_location, audio_path=None)
        paths = processed_paths(entry)
        row["transcript_path"] = paths["transcript"] if transcriber else None

        outputs = {"combined": row}
        outputs["linguistic"], outputs["audio"] = _split_row(row)
        for kind, payload in outputs.items():
            out = cache.path(f"{kind}.json")
            out.write_text(json.dumps(payload, indent=2))
            storage.upload(out, paths[kind])
        if sample.transcript_path:
            storage.upload(Path(sample.transcript_path), paths["transcript"])

    entry.local_cache_path = ""
    entry.file_status = FileStatus.PROCESSED.value
    return InterviewSample.from_row(row)
