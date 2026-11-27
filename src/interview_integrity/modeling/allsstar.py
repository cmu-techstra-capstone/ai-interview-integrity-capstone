"""Import local ALLSSTAR English audio for reading/spontaneous research.

Labels come from elicitation-task codes, not audio impressions or AI judgments.
No downloads, hosted processing, ASR, or third-party code execution are performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import shutil
import stat
import tempfile
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from .._fs import atomic_write_text
from ..audio.quality import assess_levels
from ..audio.vad import frame_levels, speech_intervals_from_levels, speech_threshold
from ..features.loudness import extract_loudness_features
from ..features.timing import compute_timing_features
from ..media import run_ffmpeg
from .audio_baseline import AUDIO_FEATURES

TASK_LABELS = {**dict.fromkeys(("HT1", "HT2", "DHR", "LPP", "NWS"), "READING"),
               **dict.fromkeys(("ST1", "ST2", "ST3", "ST4", "QNA"), "SPONTANEOUS")}
DEFAULT_TASKS = ("NWS", "ST1", "ST2")
NAME = re.compile(r"ALL_(\d+)_(M|F)_([A-Z]{3})_([A-Z]{3})_([A-Z0-9]+)\.wav", re.I)
MAX_UNPACKED_BYTES = 30 * 1024 ** 3
MAX_FILE_BYTES = 2 * 1024 ** 3


@dataclass(frozen=True)
class Recording:
    source: str
    member: str | None
    filename: str
    participant_id: str
    native_language: str
    task: str
    delivery_label: str


def parse_recording(name: str, source: str, member: str | None = None) -> Recording:
    path = PurePosixPath(name)
    match = NAME.fullmatch(path.name)
    if not match:
        raise ValueError(f"Unrecognized ALLSSTAR WAV name: {path.name}")
    speaker, _, native, language, task = (part.upper() for part in match.groups())
    if language != "ENG":
        raise ValueError(f"Non-English recording in English import: {path.name}")
    if task not in TASK_LABELS:
        raise ValueError(f"Unknown task {task}")
    parent = f"ALL_{native}_{language}_{task}"
    if path.parent.name.upper().startswith("ALL_") and path.parent.name.upper() != parent:
        raise ValueError(f"Folder/task mismatch: {name}")
    return Recording(source, member, path.name, f"ALLSSTAR:{int(speaker):03d}",
                     native, task, TASK_LABELS[task])


def inventory(source: Path) -> tuple[list[Recording], dict]:
    """Inspect an English directory or ZIP without extracting arbitrary paths."""
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.is_dir():
        files = sorted(p for p in source.rglob("*") if p.is_file())
        for path in files:
            if any(p.is_symlink() for p in (path, *path.parents) if p != source.parent):
                raise ValueError(f"Symlink input is not supported: {path.name}")
        names = [str(p.relative_to(source).as_posix()) for p in files]
        recordings = [parse_recording(n, str(source / n)) for n in names if n.lower().endswith(".wav")]
    else:
        with zipfile.ZipFile(source) as archive:
            items = archive.infolist()
            if len(items) > 20_000 or sum(i.file_size for i in items) > MAX_UNPACKED_BYTES:
                raise ValueError("Archive exceeds import safety limits")
            seen = set()
            for item in items:
                path = PurePosixPath(item.filename)
                if (path.is_absolute() or ".." in path.parts or "\\" in item.filename
                        or (path.parts and ":" in path.parts[0])
                        or stat.S_ISLNK(item.external_attr >> 16)
                        or item.file_size > MAX_FILE_BYTES):
                    raise ValueError(f"Unsafe archive member: {item.filename}")
                key = item.filename.casefold()
                if key in seen:
                    raise ValueError("Duplicate archive member")
                seen.add(key)
            names = [i.filename for i in items if not i.is_dir()]
            recordings = [parse_recording(n, str(source), n) for n in names if n.lower().endswith(".wav")]
    filenames = [r.filename.casefold() for r in recordings]
    if len(set(filenames)) != len(filenames):
        raise ValueError("Duplicate recording filename across directories")
    if not recordings:
        raise ValueError("No ALLSSTAR English WAV files found")
    language_by_speaker = {}
    for recording in recordings:
        group = recording.participant_id
        if language_by_speaker.setdefault(group, recording.native_language) != recording.native_language:
            raise ValueError(f"Speaker ID has inconsistent native-language metadata: {group}")
    return recordings, {
        "wav_files": len(recordings),
        "textgrid_files": sum(n.lower().endswith(".textgrid") for n in names),
        "participants": len(language_by_speaker),
        "task_counts": dict(sorted(Counter(r.task for r in recordings).items())),
        "label_counts_recordings": dict(Counter(r.delivery_label for r in recordings)),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _process(recording: Recording, window_seconds: float, max_windows: int) -> tuple[list, list]:
    rows, excluded = [], []
    with tempfile.TemporaryDirectory(prefix="allsstar-audio-") as directory:
        scratch = Path(directory)
        if recording.member is not None:
            raw = scratch / "source.wav"
            with zipfile.ZipFile(recording.source) as archive, archive.open(recording.member) as src, raw.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        else:
            raw = Path(recording.source)
        checksum = _sha256(raw)
        normalized = scratch / "normalized.wav"
        run_ffmpeg(["-n", "-i", str(raw), "-t", str(window_seconds * max_windows), "-vn",
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(normalized)])
        import wave
        with wave.open(str(normalized), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        n_windows = min(max_windows, int((duration + 1e-6) // window_seconds))
        if not n_windows:
            return [], [{"recording_id": Path(recording.filename).stem, "reason": "shorter_than_window"}]
        for number in range(n_windows):
            start, end = number * window_seconds, (number + 1) * window_seconds
            levels = frame_levels(normalized, start=start, end=end)
            quality = assess_levels(levels)
            intervals = speech_intervals_from_levels(levels, speech_threshold(levels))
            if quality.is_silent or not intervals:
                excluded.append({"recording_id": Path(recording.filename).stem,
                                 "window": number, "reason": "silent_or_no_separable_speech"})
                continue
            measured = compute_timing_features(speech_intervals=intervals, answer_start=start, answer_end=end)
            measured.update(extract_loudness_features(levels, intervals))
            rows.append({
                "recording_id": Path(recording.filename).stem,
                "question_id": f"W{number:04d}", "participant_id": recording.participant_id,
                "source_dataset": "allsstar", "task": recording.task,
                "window_start": start, "window_end": end,
                "video_sha256": checksum,  # Existing trainer checksum field; source is audio only.
                "audio_sha256": checksum, "audio_is_silent": quality.is_silent,
                "audio_quality": quality.to_features(),
                "features": {name: measured.get(name) for name in AUDIO_FEATURES},
            })
    return rows, excluded


def import_audio(source: Path, out: Path, *, tasks=DEFAULT_TASKS, window_seconds=30.0,
                 max_windows=4, workers=2, expected_wav=None, expected_textgrid=None,
                 expected_participants=None, verify_archive=True) -> dict:
    if out.exists():
        raise ValueError("Output directory exists; choose a new run directory")
    if (not math.isfinite(window_seconds) or window_seconds < 1 or window_seconds > 120
            or not 1 <= max_windows <= 20 or not 1 <= workers <= 4):
        raise ValueError("Window 1..120 s, max_windows 1..20 and workers 1..4 required")
    tasks = tuple(tasks)
    if not tasks or any(t not in TASK_LABELS for t in tasks):
        raise ValueError("Select known ALLSSTAR tasks")
    # Refuse to silently label interviewer speech as participant delivery.
    if "QNA" in tasks:
        raise ValueError("QNA requires candidate-only segmentation before training; not supported here")
    recordings, counts = inventory(source)
    for actual, expected in [(counts["wav_files"], expected_wav),
                             (counts["textgrid_files"], expected_textgrid),
                             (counts["participants"], expected_participants)]:
        if expected is not None and actual != expected:
            raise ValueError(f"Incomplete/unexpected corpus: expected {expected}, found {actual}")
    if verify_archive and source.is_file():
        print("Verifying archive CRC for all members...", flush=True)
        with zipfile.ZipFile(source) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"Corrupt archive member: {bad}")
    selected = [r for r in recordings if r.task in tasks]
    if set(r.delivery_label for r in selected) != {"READING", "SPONTANEOUS"}:
        raise ValueError("Selected tasks need both delivery classes")
    all_rows, excluded, failures = [], [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = [pool.submit(_process, r, window_seconds, max_windows) for r in selected]
        for index, (recording, future) in enumerate(zip(selected, pending), 1):
            try:
                rows, skipped = future.result()
                all_rows.extend(rows); excluded.extend(skipped)
            except Exception as exc:
                failures.append({"recording_id": Path(recording.filename).stem,
                                 "error": f"{type(exc).__name__}: {exc}"})
            if index == 1 or index % 25 == 0 or index == len(selected):
                print(f"Processed {index}/{len(selected)} recordings; {len(all_rows)} windows; {len(failures)} failures", flush=True)
    labels_by_recording = {Path(r.filename).stem: r.delivery_label for r in selected}
    labels = [{"recording_id": r["recording_id"], "question_id": r["question_id"],
               "participant_id": r["participant_id"],
               "delivery_label": labels_by_recording[r["recording_id"]],
               "label_source": "dataset_annotation"} for r in all_rows]
    class_counts = dict(Counter(r["delivery_label"] for r in labels))
    status = "failed" if set(class_counts) != {"READING", "SPONTANEOUS"} else "partial" if failures else "ok"
    report = {"status": status, "target": "READING_vs_SPONTANEOUS", "inventory": counts,
              "selected_tasks": list(tasks), "selected_recordings": len(selected),
              "window_seconds": window_seconds, "max_windows_per_recording": max_windows,
              "windows": len(labels), "participants_with_windows": len({r["participant_id"] for r in labels}),
              "class_counts_windows": class_counts, "excluded": excluded, "failures": failures,
              "feature_names": list(AUDIO_FEATURES),
              "warning": "Task-based delivery labels are not AI-use labels. Energy VAD is not diarization. More windows do not mean more independent speakers.",
              "complete_archive_crc_verified": bool(verify_archive and source.is_file())}
    out.mkdir(parents=True)
    atomic_write_text(out / "features.jsonl", "".join(json.dumps(r, allow_nan=False) + "\n" for r in all_rows))
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=["recording_id", "question_id", "participant_id", "delivery_label", "label_source"])
    writer.writeheader(); writer.writerows(labels)
    atomic_write_text(out / "labels.csv", text.getvalue())
    atomic_write_text(out / "inventory.json", json.dumps([asdict(r) for r in recordings], indent=2) + "\n")
    atomic_write_text(out / "quality.json", json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Downloaded ZIP or extracted English directory")
    parser.add_argument("--out-dir", required=True, type=Path, help="New ignored directory under data/processed")
    parser.add_argument("--tasks", nargs="+", default=list(DEFAULT_TASKS))
    parser.add_argument("--window-seconds", type=float, default=30)
    parser.add_argument("--max-windows", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--expect-wav", type=int)
    parser.add_argument("--expect-textgrid", type=int)
    parser.add_argument("--expect-participants", type=int)
    args = parser.parse_args()
    try:
        report = import_audio(args.source, args.out_dir, tasks=args.tasks,
                              window_seconds=args.window_seconds, max_windows=args.max_windows,
                              workers=args.workers, expected_wav=args.expect_wav,
                              expected_textgrid=args.expect_textgrid, expected_participants=args.expect_participants)
        print(json.dumps({k: report[k] for k in ("status", "windows", "participants_with_windows", "class_counts_windows")}, indent=2))
        if report["status"] != "ok":
            parser.exit(2, "ALLSSTAR import incomplete; inspect quality.json before training\n")
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"allsstar-import: {exc}\n")


if __name__ == "__main__":
    main()
