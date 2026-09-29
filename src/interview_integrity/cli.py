"""Command-line entry point: ``interview-integrity`` (or ``python -m interview_integrity``)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .datasets.io import load_jsonl, upsert_jsonl, write_csv, write_jsonl
from .datasets.splits import assign_splits, find_group_leakage
from .pipeline import PipelineConfig, process_video
from .storage.manifest import FileStatus, load_manifest, save_manifest
from .datasets.schema import InterviewSample
from .storage.remote import LocalFolderStorage
from .storage.source_archive import ArchiveSourceStorage
from .storage.sources import ADAPTERS, AccessRequired, dataset_info, load_registry, require_public
from .storage.workflow import process_manifest_entry
from .transcription.sidecar import SidecarTranscriber


def _cmd_process(args: argparse.Namespace) -> int:
    transcriber = SidecarTranscriber(args.transcript) if args.transcript else None
    config = PipelineConfig(
        interim_dir=Path(args.interim_dir),
        min_pause=args.min_pause,
        vad_threshold_dbfs=args.vad_threshold_dbfs,
        overwrite=args.overwrite,
    )
    samples = process_video(args.video, args.metadata, transcriber=transcriber, config=config)

    out_dir = Path(args.out_dir)
    all_samples = upsert_jsonl(samples, out_dir / "samples.jsonl")
    write_csv(all_samples, out_dir / "samples.csv")

    for s in samples:
        print(json.dumps(s.to_row(), indent=2))
    print(f"\nWrote {len(samples)} row(s); dataset now has {len(all_samples)} row(s) in {out_dir}/",
          file=sys.stderr)
    return 0


def _cmd_split(args: argparse.Namespace) -> int:
    path = Path(args.input)
    samples = assign_splits(load_jsonl(path), seed=args.seed, group_key=args.group_key)
    leaks = find_group_leakage(samples, args.group_key)
    if leaks:
        print(f"Leakage detected: {leaks}", file=sys.stderr)
        return 1
    write_jsonl(samples, path)
    write_csv(samples, path.with_suffix(".csv"))
    counts: dict[str, int] = {}
    for s in samples:
        counts[s.split or ""] = counts.get(s.split or "", 0) + 1
    print(f"Assigned splits grouped by {args.group_key}: {counts}")
    return 0


def _manifest_path(args: argparse.Namespace, name: str) -> Path:
    return Path(args.manifest_dir) / "files" / f"{name}.csv"


def _cmd_storage_init(args: argparse.Namespace) -> int:
    created = LocalFolderStorage(args.root).ensure_layout()
    print(f"Created {len(created)} folder(s): {created}" if created else "Layout already present; nothing changed.")
    return 0


def _cmd_datasets_status(args: argparse.Namespace) -> int:
    registry = load_registry(Path(args.manifest_dir) / "datasets.json")
    for name, info in registry["datasets"].items():
        path = _manifest_path(args, name)
        counts: dict[str, int] = {}
        if path.is_file():
            for e in load_manifest(path):
                counts[e.file_status] = counts.get(e.file_status, 0) + 1
        print(f"{name:20s} access={info['access']:10s} status={info['status']:20s} files={counts or '-'}")
    return 0


def _cmd_datasets_build_manifest(args: argparse.Namespace) -> int:
    registry = load_registry(Path(args.manifest_dir) / "datasets.json")
    info = dataset_info(args.name, registry)
    try:
        require_public(args.name, info)
    except AccessRequired as exc:
        print(exc, file=sys.stderr)
        return 2
    build, _ = ADAPTERS[args.name]
    entries = build(info)
    save_manifest(entries, _manifest_path(args, args.name))
    print(f"Wrote {len(entries)} entries to {_manifest_path(args, args.name)}")
    return 0


def _cmd_datasets_acquire(args: argparse.Namespace) -> int:
    registry = load_registry(Path(args.manifest_dir) / "datasets.json")
    info = dataset_info(args.name, registry)
    try:
        require_public(args.name, info)
    except AccessRequired as exc:
        print(exc, file=sys.stderr)
        return 2
    storage = LocalFolderStorage(args.root)
    storage.ensure_layout()
    path = _manifest_path(args, args.name)
    entries = load_manifest(path)
    selected = entries[: args.limit] if args.limit else entries
    _, mirror = ADAPTERS[args.name]
    result = mirror(info, selected, storage)
    save_manifest(entries, path)
    print(f"uploaded={result.uploaded} skipped={result.skipped} "
          f"MB_uploaded={result.bytes_uploaded / 2**20:.1f} MB_fetched={result.bytes_fetched / 2**20:.1f}")
    return 0


def _cmd_process_remote(args: argparse.Namespace) -> int:
    storage = LocalFolderStorage(args.root)
    path = _manifest_path(args, args.dataset)
    entries = load_manifest(path)
    todo = [e for e in entries if (not args.video_id or e.video_id in args.video_id)
            and e.file_status in (FileStatus.IN_DRIVE.value, FileStatus.PROCESSED.value)]
    if args.limit:
        todo = todo[: args.limit]
    samples = []
    try:
        for e in todo:
            samples.append(process_manifest_entry(
                e, storage, cache_root=args.cache_dir, max_cache_bytes=int(args.max_cache_mb * 2**20)
            ))
            print(f"processed {e.video_id}", file=sys.stderr)
    finally:
        save_manifest(entries, path)
    if samples:
        all_samples = upsert_jsonl(samples, Path(args.out_dir) / "samples.jsonl")
        write_csv(all_samples, Path(args.out_dir) / "samples.csv")
    print(f"Processed {len(samples)} file(s)")
    return 0


def _collect_combined_csv(out: LocalFolderStorage, dataset: str) -> int:
    prefix = f"processed/combined_features/{dataset}"
    rows = [json.loads((out.root / p).read_text()) for p in out.list(prefix) if p.endswith(".json")]
    write_csv([InterviewSample.from_row(r) for r in rows], out.root / f"{prefix}.csv")
    return len(rows)


def _cmd_process_source(args: argparse.Namespace) -> int:
    registry = load_registry(Path(args.manifest_dir) / "datasets.json")
    info = dataset_info(args.dataset, registry)
    try:
        require_public(args.dataset, info)
    except AccessRequired as exc:
        print(exc, file=sys.stderr)
        return 2
    path = _manifest_path(args, args.dataset)
    entries = load_manifest(path)
    source = ArchiveSourceStorage.from_manifest(info["download_url"], entries)
    out = LocalFolderStorage(args.out_root)

    todo = [e for e in entries if not args.video_id or e.video_id in args.video_id]
    if not args.force:
        todo = [e for e in todo if not out.exists(f"processed/combined_features/{e.dataset_name}/{e.video_id}.json")]
    if args.limit:
        todo = todo[: args.limit]

    done, failed = 0, []
    try:
        for i, e in enumerate(todo, 1):
            try:
                process_manifest_entry(
                    e, source, output_storage=out,
                    cache_root=args.cache_dir, max_cache_bytes=int(args.max_cache_mb * 2**20),
                )
                done += 1
                print(f"[{i}/{len(todo)}] {e.video_id}", file=sys.stderr)
            except Exception as exc:  # keep going; record the failure in the manifest
                e.file_status = FileStatus.ERROR.value
                e.notes = f"processing error: {exc}"[:300]
                failed.append(e.video_id)
                print(f"[{i}/{len(todo)}] {e.video_id} FAILED: {exc}", file=sys.stderr)
    finally:
        save_manifest(entries, path)
        total = _collect_combined_csv(out, args.dataset)
    print(f"Processed {done}, failed {len(failed)} {failed or ''}; {total} rows in "
          f"processed/combined_features/{args.dataset}.csv; fetched {source.bytes_fetched / 2**20:.1f} MB from source")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="interview-integrity", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("process", help="Process one interview video into dataset rows")
    p.add_argument("--video", required=True, help="Path to the interview video")
    p.add_argument("--metadata", required=True, help="Path to the recording metadata JSON")
    p.add_argument("--transcript", help="Existing transcript (.json or .txt). Omit to skip linguistic features.")
    p.add_argument("--interim-dir", default="data/interim")
    p.add_argument("--out-dir", default="data/processed")
    p.add_argument("--min-pause", type=float, default=0.3, help="Minimum silence (s) counted as a pause")
    p.add_argument("--vad-threshold-dbfs", type=float, default=None,
                   help="Fixed VAD threshold; default adapts to each recording's level")
    p.add_argument("--overwrite", action="store_true", help="Re-extract audio even if it exists")
    p.set_defaults(func=_cmd_process)

    s = sub.add_parser("split", help="Assign group-aware train/val/test splits in place")
    s.add_argument("--input", default="data/processed/samples.jsonl")
    s.add_argument("--group-key", default="participant_id", choices=["participant_id", "recording_id"])
    s.add_argument("--seed", type=int, default=13)
    s.set_defaults(func=_cmd_split)

    st = sub.add_parser("storage-init", help="Create the shared project folder layout (never deletes)")
    st.add_argument("--root", required=True, help="Shared root folder (e.g. Drive for Desktop mount)")
    st.set_defaults(func=_cmd_storage_init)

    ds = sub.add_parser("datasets", help="Dataset registry, manifests and acquisition")
    ds.add_argument("--manifest-dir", default="manifests")
    ds_sub = ds.add_subparsers(dest="datasets_command", required=True)
    d = ds_sub.add_parser("status", help="Show access/status for each dataset")
    d.set_defaults(func=_cmd_datasets_status)
    d = ds_sub.add_parser("build-manifest", help="Build a file manifest from the official source (public only)")
    d.add_argument("name")
    d.set_defaults(func=_cmd_datasets_build_manifest)
    d = ds_sub.add_parser("acquire", help="Stream a public dataset from its official source into shared storage")
    d.add_argument("name")
    d.add_argument("--root", required=True, help="Shared root folder")
    d.add_argument("--limit", type=int, help="Only the first N files (for a trial run)")
    d.set_defaults(func=_cmd_datasets_acquire)

    r = sub.add_parser("process-remote", help="Fetch files from shared storage to a temp cache, process, upload outputs")
    r.add_argument("--dataset", required=True)
    r.add_argument("--root", required=True, help="Shared root folder")
    r.add_argument("--video-id", nargs="*", help="Specific video IDs (default: all in storage)")
    r.add_argument("--limit", type=int)
    r.add_argument("--manifest-dir", default="manifests")
    r.add_argument("--cache-dir", help="Parent dir for the temp cache (default: system temp)")
    r.add_argument("--max-cache-mb", type=float, default=500)
    r.add_argument("--out-dir", default="data/processed")
    r.set_defaults(func=_cmd_process_remote)

    ps = sub.add_parser("process-source",
                        help="Stream clips one at a time from the official source, process, keep only outputs")
    ps.add_argument("--dataset", required=True)
    ps.add_argument("--video-id", nargs="*")
    ps.add_argument("--limit", type=int)
    ps.add_argument("--force", action="store_true", help="Reprocess clips that already have outputs")
    ps.add_argument("--manifest-dir", default="manifests")
    ps.add_argument("--out-root", default=".", help="Outputs go to <out-root>/processed/... (default: repo root)")
    ps.add_argument("--cache-dir", help="Parent dir for the temp cache (default: system temp)")
    ps.add_argument("--max-cache-mb", type=float, default=500)
    ps.set_defaults(func=_cmd_process_source)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
