"""Run the follow-up pattern on the MIT Interview Dataset (exploratory, no AI-use labels).

Steps per recording:
  1. ffmpeg -> temporary 16 kHz mono WAV (deleted after ASR)
  2. faster-whisper word timestamps (cached as JSON under data/processed/fusion/asr/)
  3. align ASR words to the speaker-labelled MIT transcript -> answer windows
  4. join with the relative head/gaze timeline from experiments/video/relative_events.py
  5. deterministic follow-up pattern per answer

MIT interviews were not AI-assisted, so the rate at which the rule fires here is an
estimate of how often it would flag ordinary answers (a false-positive proxy), not an
accuracy figure. Per-recording outputs stay in ignored data/ paths; only aggregate
counts are written to reports/.

Usage (from the worktree root):
  PYTHONPATH=src python experiments/fusion/run_mit.py asr --model <faster-whisper dir>
  PYTHONPATH=src python experiments/fusion/run_mit.py evaluate
  PYTHONPATH=src python experiments/fusion/run_mit.py summarize
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import Counter
from dataclasses import replace
from pathlib import Path

from interview_integrity.fusion.followup import (
    INSUFFICIENT, MET, NO_PATTERN, NOT_MET, REQUIRED, SUGGEST, UNMEASURABLE,
    FollowupConfig, VisualTrack, evaluate_interview,
)
from interview_integrity.fusion.turns import Word, align_turns, build_answer_windows, parse_turker_transcript

ROOT = Path(__file__).resolve().parents[2]
MIT = ROOT / "data/raw/video_research/mit"
VIDEO_OUT = ROOT / "data/processed/video_research"
OUT = ROOT / "data/processed/fusion"
csv.field_size_limit(10**8)


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "run.log", "a") as f:
        f.write(line + "\n")


def load_transcripts(labels_zip: Path) -> dict[str, str]:
    with zipfile.ZipFile(labels_zip) as z:
        raw = z.read("Labels/interview_transcripts_by_turkers.csv").decode("utf-8", errors="replace")
    out = {}
    for row in csv.reader(io.StringIO(raw)):
        if len(row) >= 2 and row[0].strip():
            out[row[0].strip().lower()] = ",".join(row[1:])
    return out


def stems(videos: Path, only: list[str] | None, limit: int | None) -> list[str]:
    names = sorted(p.stem for p in videos.glob("*.avi"))
    if only:
        names = [n for n in names if n in set(only)]
    return names[:limit] if limit else names


# ------------------------------------------------------------------ ASR

def run_asr(args) -> None:
    from faster_whisper import WhisperModel  # optional dependency, only needed here

    model = WhisperModel(str(args.model), device="cpu", compute_type="int8", cpu_threads=args.threads)
    asr_dir = OUT / "asr"
    asr_dir.mkdir(parents=True, exist_ok=True)
    todo = [s for s in stems(MIT / "videos", args.only, args.limit) if not (asr_dir / f"{s}.json").exists()]
    log(f"asr: {len(todo)} recordings to transcribe with {args.model.name}")
    for k, stem in enumerate(todo, 1):
        t0 = time.time()
        with tempfile.TemporaryDirectory(prefix="iic-asr-") as tmp:
            wav = Path(tmp) / "a.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(MIT / "videos" / f"{stem}.avi"),
                            "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
            segments, info = model.transcribe(
                str(wav), language="en", word_timestamps=True, vad_filter=True,
                beam_size=args.beam, condition_on_previous_text=False)
            words = [{"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
                     for seg in segments for w in (seg.words or [])]
        tmp_path = asr_dir / f"{stem}.json.part"
        tmp_path.write_text(json.dumps({"model": args.model.name, "beam_size": args.beam,
                                        "duration_s": info.duration, "words": words}))
        tmp_path.rename(asr_dir / f"{stem}.json")
        log(f"asr {k}/{len(todo)} {stem}: {len(words)} words, {info.duration:.0f}s audio in {time.time() - t0:.0f}s")


# ------------------------------------------------------------------ evaluate

def load_track(recording_id: str) -> VisualTrack | None:
    d = VIDEO_OUT / "mit_full_relative" / recording_id
    if not (d / "timeline.json").exists():
        return None
    timeline = json.loads((d / "timeline.json").read_text())
    with open(d / "measurements.jsonl") as f:
        measurements = [json.loads(line) for line in f if line.strip()]
    return VisualTrack.from_timeline(timeline, measurements)


def windows_for(stem: str, transcripts: dict[str, str]):
    asr = json.loads((OUT / "asr" / f"{stem}.json").read_text())
    words = [Word(w["text"], w["start"], w["end"]) for w in asr["words"]]
    turns = parse_turker_transcript(transcripts.get(stem.lower(), ""))
    return build_answer_windows(align_turns(turns, words))


def run_evaluate(args) -> None:
    transcripts = load_transcripts(MIT / "Labels.zip")
    inv = json.loads((VIDEO_OUT / "mit_full" / "inventory.json").read_text())
    rec_ids = {Path(v["relative_path"]).stem: v["recording_id"] for v in inv["videos"]}
    res_dir = OUT / "results"
    res_dir.mkdir(parents=True, exist_ok=True)
    cfg = FollowupConfig(min_latency_s=args.min_latency, look_window_into_answer_s=args.look_window)
    n = 0
    for stem in stems(MIT / "videos", args.only, args.limit):
        if not (OUT / "asr" / f"{stem}.json").exists():
            continue
        windows = windows_for(stem, transcripts)
        track = load_track(rec_ids[stem]) if stem in rec_ids else None
        results = evaluate_interview(stem, windows, track, cfg)
        with open(res_dir / f"{stem}.jsonl", "w") as f:
            for w, r in zip(windows, results):
                row = r.to_dict(include_text=True)
                row["latency_s"] = w.latency
                row["timing_ok"] = w.timing_ok
                f.write(json.dumps(row) + "\n")
        n += 1
    log(f"evaluate: wrote results for {n} recordings (min_latency={cfg.min_latency_s}, look_window={cfg.look_window_into_answer_s})")


# ------------------------------------------------------------------ summarize

def _counts(results) -> dict:
    status = Counter(r.status for r in results)
    measurable = status[SUGGEST] + status[NO_PATTERN]
    return {"answers": len(results), "status": dict(status),
            "fully_measurable": measurable,
            "suggest_rate_among_fully_measurable": round(status[SUGGEST] / measurable, 4) if measurable else None}


def run_summarize(args) -> None:
    transcripts = load_transcripts(MIT / "Labels.zip")
    inv = json.loads((VIDEO_OUT / "mit_full" / "inventory.json").read_text())
    rec_ids = {Path(v["relative_path"]).stem: v["recording_id"] for v in inv["videos"]}
    names = [s for s in stems(MIT / "videos", args.only, args.limit) if (OUT / "asr" / f"{s}.json").exists()]
    data = []
    for stem in names:
        data.append((stem, windows_for(stem, transcripts), load_track(rec_ids[stem]) if stem in rec_ids else None))

    base = FollowupConfig()
    results = [r for stem, ws, tr in data for r in evaluate_interview(stem, ws, tr, base)]
    all_windows = [w for _, ws, _ in data for w in ws]
    cond = {}
    for name in REQUIRED + ("read_like_delivery", "ai_like_text"):
        c = Counter(r.condition(name).status for r in results)
        m = c[MET] + c[NOT_MET]
        cond[name] = {"met": c[MET], "not_met": c[NOT_MET], "unmeasurable": c[UNMEASURABLE],
                      "met_rate_among_measurable": round(c[MET] / m, 4) if m else None}
    latencies = [w.latency for w in all_windows if w.timing_ok and w.latency is not None]
    per_rec = Counter(r.recording_id for r in results if r.status == SUGGEST)

    grid = []
    for lat in (1.0, 1.5, 2.0, 3.0):
        for look in (2.0, 3.0, 5.0):
            cfg = replace(base, min_latency_s=lat, look_window_into_answer_s=look)
            rs = [r for stem, ws, tr in data for r in evaluate_interview(stem, ws, tr, cfg)]
            grid.append({"min_latency_s": lat, "look_window_into_answer_s": look, **_counts(rs)})

    q = statistics.quantiles(latencies, n=20) if len(latencies) >= 20 else []
    summary = {
        "type": "exploratory; MIT interviews have no AI-assistance labels",
        "interpretation": "suggest rate on ordinary interviews approximates how often the rule flags normal answers",
        "ai_assistance_probability": None,
        "recordings": len(names),
        "recordings_with_visual_timeline": sum(1 for _, _, tr in data if tr is not None),
        "answer_windows": len(all_windows),
        "windows_with_reliable_timing": sum(w.timing_ok for w in all_windows),
        "latency_s": {"n": len(latencies),
                      "median": round(statistics.median(latencies), 3) if latencies else None,
                      "p10": round(q[1], 3) if q else None, "p90": round(q[17], 3) if q else None,
                      "share_ge_2s": round(sum(l >= 2 for l in latencies) / len(latencies), 4) if latencies else None},
        "default_config": vars(base) if hasattr(base, "__dict__") else base.__dict__,
        "default_result": _counts(results),
        "conditions": cond,
        "recordings_with_any_suggestion": len(per_rec),
        "max_suggestions_in_one_recording": max(per_rec.values(), default=0),
        "sensitivity_grid": grid,
        "asr_model": json.loads((OUT / "asr" / f"{names[0]}.json").read_text())["model"] if names else None,
    }
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    log(f"summarize: {len(results)} answers from {len(names)} recordings -> {out}")
    print(json.dumps(summary, indent=2, default=str))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("asr", "evaluate", "summarize"):
        s = sub.add_parser(name)
        s.add_argument("--only", nargs="*", help="recording stems, e.g. P1 PP1")
        s.add_argument("--limit", type=int)
        if name == "asr":
            s.add_argument("--model", type=Path, required=True)
            s.add_argument("--threads", type=int, default=4)
            s.add_argument("--beam", type=int, default=1)
        if name == "evaluate":
            s.add_argument("--min-latency", type=float, default=2.0)
            s.add_argument("--look-window", type=float, default=3.0)
        if name == "summarize":
            s.add_argument("--report", default=str(ROOT / "reports/fusion/mit-followup-pattern-20261105.json"))
    args = p.parse_args(argv)
    {"asr": run_asr, "evaluate": run_evaluate, "summarize": run_summarize}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
