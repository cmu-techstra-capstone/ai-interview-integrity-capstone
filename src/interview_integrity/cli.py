"""Command-line entry point: ``interview-integrity`` (or ``python -m interview_integrity``)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .datasets.io import load_jsonl, upsert_jsonl, write_csv, write_jsonl
from .datasets.splits import assign_splits, find_group_leakage
from .pipeline import PipelineConfig, process_video
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
    p.add_argument("--vad-threshold-dbfs", type=float, default=-40.0)
    p.add_argument("--overwrite", action="store_true", help="Re-extract audio even if it exists")
    p.set_defaults(func=_cmd_process)

    s = sub.add_parser("split", help="Assign group-aware train/val/test splits in place")
    s.add_argument("--input", default="data/processed/samples.jsonl")
    s.add_argument("--group-key", default="participant_id", choices=["participant_id", "recording_id"])
    s.add_argument("--seed", type=int, default=13)
    s.set_defaults(func=_cmd_split)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
