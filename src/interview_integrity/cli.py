"""Command-line entry point: ``interview-integrity`` (or ``python -m interview_integrity``).

A thin wrapper: parses arguments, calls ``services`` and prints results. All logic lives
in ``services`` so a future API can reuse it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import services
from .config import Settings
from .pipeline import PipelineConfig
from .storage.sources import AccessRequired
from .transcription.sidecar import SidecarTranscriber

EXIT_OK, EXIT_FAILED, EXIT_ACCESS = 0, 1, 2


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _stt(args: argparse.Namespace):
    if not getattr(args, "stt", None):
        return None
    from .transcription.registry import create_transcriber, parse_options

    return create_transcriber(args.stt, **parse_options(args.stt_option))


def _pipeline_config(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        interim_dir=Path(args.interim_dir),
        min_pause=args.min_pause,
        vad_threshold_dbfs=args.vad_threshold_dbfs,
        overwrite=getattr(args, "overwrite", False),
    )


def _print_issue_summary(issues) -> None:
    if not issues:
        return
    errors = sum(i.severity == "error" for i in issues)
    _err(f"quality: {errors} error(s), {len(issues) - errors} warning(s)")
    for i in issues:
        _err(f"  [{i.severity}] {i.code} {i.key}: {i.message}")


def _print_batch(result: services.BatchResult, what: str) -> int:
    for name, reason in result.failed.items():
        _err(f"FAILED {name}: {reason}")
    _print_issue_summary(result.issues)
    extra = "".join(f"; {k}={v}" for k, v in result.extra.items())
    print(f"{what}: processed {len(result.processed)}, failed {len(result.failed)}; "
          f"{len(result.samples)} new row(s); dataset rows {result.dataset_rows}{extra}")
    return EXIT_OK if result.ok else EXIT_FAILED


# ----------------------------------------------------------------------------- commands

def _cmd_process(args):
    transcriber = SidecarTranscriber(args.transcript) if args.transcript else _stt(args)
    result = services.process_local_video(args.video, args.metadata, transcriber=transcriber,
                                          out_dir=args.out_dir, config=_pipeline_config(args))
    for s in result.samples:
        print(json.dumps(s.to_row(), indent=2))
    _print_issue_summary(result.issues)
    _err(f"\nWrote {len(result.samples)} row(s); dataset now has {result.dataset_rows} row(s) in {result.out_dir}/")
    return EXIT_OK


def _cmd_process_batch(args):
    result = services.process_local_batch(args.dir, out_dir=args.out_dir, config=_pipeline_config(args),
                                          transcriber=_stt(args))
    _err(f"quality report: {Path(args.out_dir) / 'batch_quality_report.json'}")
    return _print_batch(result, "batch")


def _cmd_split(args):
    try:
        counts = services.assign_dataset_splits(args.input, seed=args.seed, group_key=args.group_key)
    except services.LeakageError as exc:
        _err(str(exc))
        return EXIT_FAILED
    print(f"Assigned splits (grouped by {args.group_key} + recording + source video): {counts}")
    return EXIT_OK


def _cmd_storage_init(args):
    created = services.init_storage(args.root)
    print(f"Created {len(created)} folder(s): {created}" if created else "Layout already present; nothing changed.")
    return EXIT_OK


def _cmd_datasets_status(args):
    for d in services.dataset_status(args.manifest_dir):
        print(f"{d.name:20s} access={d.access:10s} status={d.status:20s} files={d.file_counts or '-'}")
    return EXIT_OK


def _cmd_datasets_build_manifest(args):
    n = services.build_dataset_manifest(args.name, args.manifest_dir)
    print(f"Wrote {n} entries to {Path(args.manifest_dir) / 'files' / (args.name + '.csv')}")
    return EXIT_OK


def _cmd_datasets_acquire(args):
    r = services.acquire_dataset(args.name, args.root, manifest_dir=args.manifest_dir, limit=args.limit)
    print(f"uploaded={r.uploaded} skipped={r.skipped} "
          f"MB_uploaded={r.bytes_uploaded / 2**20:.1f} MB_fetched={r.bytes_fetched / 2**20:.1f}")
    return EXIT_OK


def _cmd_process_remote(args):
    result = services.process_from_storage(
        args.dataset, args.root, manifest_dir=args.manifest_dir, video_ids=args.video_id, limit=args.limit,
        cache_dir=args.cache_dir, max_cache_bytes=int(args.max_cache_mb * 2**20), out_dir=args.out_dir,
    )
    return _print_batch(result, "process-remote")


def _cmd_process_source(args):
    result = services.process_from_source(
        args.dataset, manifest_dir=args.manifest_dir, out_root=args.out_root, video_ids=args.video_id,
        limit=args.limit, force=args.force, cache_dir=args.cache_dir,
        max_cache_bytes=int(args.max_cache_mb * 2**20),
    )
    return _print_batch(result, "process-source")


def _cmd_quality(args):
    report = services.run_quality(args.input, args.report)
    print(f"{report['samples']} samples: {report['errors']} error(s), {report['warnings']} warning(s)")
    for severity, codes in report["by_code"].items():
        for code, n in codes.items():
            print(f"  {severity:7s} {code:28s} {n}")
    if args.verbose:
        for i in report["issues"]:
            print(f"  [{i['severity']}] {i['code']} {i['key']}: {i['message']}")
    failing = report["errors"] + (report["warnings"] if args.fail_on == "warning" else 0)
    return EXIT_FAILED if failing else EXIT_OK


def _cmd_stt_eval(args):
    report = services.evaluate_stt(args.reference, args.hypothesis, args.report)
    print(json.dumps({k: v for k, v in report.items() if k != "per_clip"}, indent=2))
    return EXIT_OK


def _cmd_stt_list(args):
    from .transcription.registry import TRANSCRIBERS

    for name, (_, desc) in TRANSCRIBERS.items():
        print(f"{name:16s} {desc}")
    return EXIT_OK


def _cmd_stt_benchmark(args):
    report = services.run_stt_benchmark(
        args.candidates, dataset=args.dataset, audio_dir=args.audio_dir, reference_dir=args.reference_dir,
        manifest_dir=args.manifest_dir, limit=args.limit, allow_external_upload=args.allow_external_upload,
        cache_dir=args.cache_dir, max_cache_bytes=int(args.max_cache_mb * 2**20), report_path=args.report,
    )
    for r in report["results"]:
        c = r["candidate"]["name"]
        if r["status"] != "ok":
            print(f"{c:24s} {r['status']}: {r.get('reason')}")
        else:
            print(f"{c:24s} WER={r.get('corpus_wer')} filler_recall={r.get('filler_recall')} "
                  f"word_ts={r.get('word_timestamp_coverage')} speakers={r.get('speaker_label_coverage')} "
                  f"RTF={r.get('real_time_factor')} peakRSS={r.get('peak_process_rss_mb')}MB")
    return EXIT_OK


def _cmd_staged_template(args):
    from .staged import parse_condition_args

    services.staged_template(args.interview_id, args.participant_id, args.question_bank,
                             parse_condition_args(args.condition), args.out)
    print(f"Wrote {args.out}")
    return EXIT_OK


def _cmd_staged_import_labels(args):
    services.staged_import_labels(args.metadata, args.labels, args.out)
    print(f"Updated timestamps in {args.out or args.metadata}")
    return EXIT_OK


def _cmd_staged_validate(args):
    failing = 0
    for path in args.metadata:
        issues = services.staged_validate(path)
        errors = [i for i in issues if i.severity == "error"]
        print(f"{path}: {len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
        for i in issues:
            print(f"  [{i.severity}] {i.code}: {i.message}")
        failing += len(errors)
    return EXIT_FAILED if failing else EXIT_OK


def _cmd_cache_clean(args):
    removed = services.clean_caches(args.cache_dir, args.older_than_hours)
    print(f"Removed {len(removed)} stale cache dir(s)")
    return EXIT_OK


# ----------------------------------------------------------------------------- parser

def _add_pipeline_args(p: argparse.ArgumentParser, settings: Settings) -> None:
    p.add_argument("--interim-dir", default=str(settings.interim_dir))
    p.add_argument("--out-dir", default=str(settings.out_dir))
    p.add_argument("--min-pause", type=float, default=0.3, help="Minimum silence (s) counted as a pause")
    p.add_argument("--vad-threshold-dbfs", type=float, default=None,
                   help="Fixed VAD threshold; default adapts to each recording's level")
    p.add_argument("--stt", help="Optional STT candidate when no transcript file is given (see 'stt-list')")
    p.add_argument("--stt-option", action="append", metavar="KEY=VALUE", help="Option for the STT candidate")


def _add_cache_args(p: argparse.ArgumentParser, settings: Settings) -> None:
    p.add_argument("--cache-dir", default=str(settings.cache_dir) if settings.cache_dir else None,
                   help="Parent dir for the temp cache (default: system temp)")
    p.add_argument("--max-cache-mb", type=float, default=settings.max_cache_mb)


def build_parser(settings: Settings | None = None) -> argparse.ArgumentParser:
    settings = settings or Settings.from_env()
    manifests = str(settings.manifest_dir)
    parser = argparse.ArgumentParser(prog="interview-integrity", description=__doc__)
    parser.add_argument("--log-level", default=settings.log_level, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("process", help="Process one interview video into dataset rows")
    p.add_argument("--video", required=True, help="Path to the interview video")
    p.add_argument("--metadata", required=True, help="Path to the recording metadata JSON")
    p.add_argument("--transcript", help="Existing transcript (.json or .txt)")
    p.add_argument("--overwrite", action="store_true", help="Re-extract audio even if it exists")
    _add_pipeline_args(p, settings)
    p.set_defaults(func=_cmd_process)

    b = sub.add_parser("process-batch", help="Process every <name>.metadata.json + <name>.<video> in a directory")
    b.add_argument("--dir", required=True)
    _add_pipeline_args(b, settings)
    b.set_defaults(func=_cmd_process_batch)

    s = sub.add_parser("split", help="Assign leakage-safe train/val/test splits in place")
    s.add_argument("--input", default=str(settings.out_dir / "samples.jsonl"))
    s.add_argument("--group-key", default="participant_id", choices=["participant_id", "recording_id"])
    s.add_argument("--seed", type=int, default=13)
    s.set_defaults(func=_cmd_split)

    st = sub.add_parser("storage-init", help="Create the shared project folder layout (never deletes)")
    st.add_argument("--root", required=settings.shared_root is None,
                    default=str(settings.shared_root) if settings.shared_root else None)
    st.set_defaults(func=_cmd_storage_init)

    ds = sub.add_parser("datasets", help="Dataset registry, manifests and acquisition")
    ds.add_argument("--manifest-dir", default=manifests)
    ds_sub = ds.add_subparsers(dest="datasets_command", required=True)
    d = ds_sub.add_parser("status", help="Show access/status for each dataset")
    d.set_defaults(func=_cmd_datasets_status)
    d = ds_sub.add_parser("build-manifest", help="Build a file manifest from the official source (public only)")
    d.add_argument("name")
    d.set_defaults(func=_cmd_datasets_build_manifest)
    d = ds_sub.add_parser("acquire", help="Stream a public dataset from its official source into shared storage")
    d.add_argument("name")
    d.add_argument("--root", required=settings.shared_root is None,
                   default=str(settings.shared_root) if settings.shared_root else None)
    d.add_argument("--limit", type=int, help="Only the first N files (for a trial run)")
    d.set_defaults(func=_cmd_datasets_acquire)

    r = sub.add_parser("process-remote", help="Fetch from shared storage to a temp cache, process, upload outputs")
    r.add_argument("--dataset", required=True)
    r.add_argument("--root", required=settings.shared_root is None,
                   default=str(settings.shared_root) if settings.shared_root else None)
    r.add_argument("--video-id", nargs="*", help="Specific video IDs (default: all in storage)")
    r.add_argument("--limit", type=int)
    r.add_argument("--manifest-dir", default=manifests)
    r.add_argument("--out-dir", default=str(settings.out_dir))
    _add_cache_args(r, settings)
    r.set_defaults(func=_cmd_process_remote)

    ps = sub.add_parser("process-source",
                        help="Stream clips one at a time from the official source, process, keep only outputs")
    ps.add_argument("--dataset", required=True)
    ps.add_argument("--video-id", nargs="*")
    ps.add_argument("--limit", type=int)
    ps.add_argument("--force", action="store_true", help="Reprocess clips that already have outputs")
    ps.add_argument("--manifest-dir", default=manifests)
    ps.add_argument("--out-root", default=".", help="Outputs go to <out-root>/processed/... (default: repo root)")
    _add_cache_args(ps, settings)
    ps.set_defaults(func=_cmd_process_source)

    qc = sub.add_parser("quality", help="Run dataset quality checks (exit 1 on errors)")
    qc.add_argument("--input", required=True, help="samples .jsonl or a directory of row JSON files")
    qc.add_argument("--report", help="Write the full report as JSON")
    qc.add_argument("--fail-on", choices=["error", "warning"], default="error")
    qc.add_argument("-v", "--verbose", action="store_true", help="List every issue")
    qc.set_defaults(func=_cmd_quality)

    ev = sub.add_parser("stt-eval", help="Score STT transcripts against reference transcripts (WER, fillers)")
    ev.add_argument("--reference", required=True, help="Directory of reference transcripts (.txt/.json)")
    ev.add_argument("--hypothesis", required=True, help="Directory of STT output, same file stems")
    ev.add_argument("--report", help="Write the full per-clip report as JSON")
    ev.set_defaults(func=_cmd_stt_eval)

    sl = sub.add_parser("stt-list", help="List transcriber adapters (candidates; none is the default)")
    sl.set_defaults(func=_cmd_stt_list)

    sb = sub.add_parser("stt-benchmark", help="Benchmark STT candidates (heavy: run on a machine with disk space)")
    sb.add_argument("--candidates", required=True, help="Candidate config JSON (see config/stt_candidates.example.json)")
    src = sb.add_mutually_exclusive_group(required=True)
    src.add_argument("--dataset", help="Public dataset with reference transcripts, streamed (e.g. michigan_deception)")
    src.add_argument("--audio-dir", help="Local audio/video files; pair with --reference-dir by file stem")
    sb.add_argument("--reference-dir")
    sb.add_argument("--manifest-dir", default=manifests)
    sb.add_argument("--limit", type=int, default=20)
    sb.add_argument("--allow-external-upload", action="store_true",
                    help="Permit candidates that send audio to a third party (requires project approval)")
    sb.add_argument("--report", help="Write the full report as JSON")
    _add_cache_args(sb, settings)
    sb.set_defaults(func=_cmd_stt_benchmark)

    sg = sub.add_parser("staged", help="Staged-interview metadata tools")
    sg_sub = sg.add_subparsers(dest="staged_command", required=True)
    t = sg_sub.add_parser("template", help="Write a metadata skeleton for one recording")
    t.add_argument("--interview-id", required=True)
    t.add_argument("--participant-id", required=True)
    t.add_argument("--question-bank", required=True, help="JSON list of {question_id, question_text}")
    t.add_argument("--condition", action="append", metavar="QID=LABEL", help="e.g. Q01=AI_VERBATIM (repeatable)")
    t.add_argument("--out", required=True)
    t.set_defaults(func=_cmd_staged_template)
    il = sg_sub.add_parser("import-labels", help="Fill question/answer timestamps from a TSV label file")
    il.add_argument("--metadata", required=True)
    il.add_argument("--labels", required=True, help="start<TAB>end<TAB>'Q01 question'|'Q01 answer'")
    il.add_argument("--out", help="Default: update --metadata in place")
    il.set_defaults(func=_cmd_staged_import_labels)
    v = sg_sub.add_parser("validate", help="Protocol checks for staged metadata files (exit 1 on errors)")
    v.add_argument("metadata", nargs="+")
    v.set_defaults(func=_cmd_staged_validate)

    cc = sub.add_parser("cache-clean", help="Remove stale iic-cache-* temp dirs left by killed runs")
    cc.add_argument("--cache-dir", default=str(settings.cache_dir) if settings.cache_dir else None)
    cc.add_argument("--older-than-hours", type=float, default=12.0)
    cc.set_defaults(func=_cmd_cache_clean)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    try:
        return args.func(args)
    except AccessRequired as exc:
        _err(str(exc))
        return EXIT_ACCESS


if __name__ == "__main__":
    raise SystemExit(main())
