"""Post-interview analysis of ONE recorded interview -> one dashboard JSON.

  video + speaker-labelled transcript
    -> head/gaze measurements (MediaPipe + MobileOne-S0 gaze, 2 fps)
    -> look-away events relative to the candidate's own first-30 s baseline
    -> answer windows (transcript timestamps, or faster-whisper words aligned to the transcript)
    -> follow-up pattern per answer -> optional GPT reviewer brief -> JSON

Run from the worktree root with the video environment (.venv-video on the Mac):

  # MIT demo (reuses cached measurements and ASR words when present):
  .venv-video/bin/python experiments/fusion/analyze_video.py data/raw/video_research/mit/videos/P1.avi \
      --transcript mit:P1 --brief --out data/processed/analyze/P1.json

  # Any recording with a JSON transcript (see fusion/transcript_input.py for formats):
  .venv-video/bin/python experiments/fusion/analyze_video.py interview.mp4 \
      --transcript interview_transcript.json --interviewer-name "Aditi Adgaonkar"

  # Self-recorded test: questions read aloud from a list, no transcript needed (uses faster-whisper):
  .venv-video/bin/python experiments/fusion/analyze_video.py data/raw/selftest/selftest1.mov \
      --questions experiments/fusion/selftest_questions.txt --brief

Outputs stay in ignored data/ paths. The JSON never contains a probability or a verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "video"))
sys.path.insert(0, str(ROOT / "experiments" / "fusion"))

from interview_integrity.fusion.analyze import analyze_recording  # noqa: E402
from interview_integrity.fusion.followup import FollowupConfig, VisualTrack  # noqa: E402
from interview_integrity.fusion.question_locate import load_questions, locate_questions  # noqa: E402
from interview_integrity.fusion.transcript_input import load_transcript, needs_asr  # noqa: E402
from interview_integrity.fusion.turns import Word, parse_turker_transcript  # noqa: E402

MODELS = ROOT / "data/models/video_research"
CLASSIFIERS = ROOT / "data/processed/video_research/phase3"
DEFAULT_ASR = ROOT.parent / "ai-interview-integrity-capstone/.cache/models/faster-whisper-base.en"
MIT = ROOT / "data/raw/video_research/mit"
FILLER_PROMPT = "Umm, so, uh, I think, like, hmm... Okay, um, let me think about that."


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ transcript

def get_turns(spec: str, interviewer_names: list[str]):
    if spec.startswith("mit:"):
        from run_mit import load_transcripts
        stem = spec[4:]
        text = load_transcripts(MIT / "Labels.zip").get(stem.lower())
        if not text:
            raise SystemExit(f"no MIT transcript for {stem}")
        return parse_turker_transcript(text)
    return load_transcript(spec, interviewer_names)


# ------------------------------------------------------------------ visual

def mit_measurement_dir(video: Path) -> Path | None:
    inv = ROOT / "data/processed/video_research/mit_full/inventory.json"
    if not inv.exists():
        return None
    for v in json.loads(inv.read_text())["videos"]:
        if v["relative_path"] == video.name:
            d = inv.parent / v["recording_id"]
            return d if (d / "measurements.jsonl").exists() and (d / "timeline.json").exists() else None
    return None


def raw_measurements(video: Path, work: Path, video_sha: str, sample_fps: float, reuse: Path | None):
    """(rows, raw_timeline). Reuses a matching cache or precomputed dir; otherwise runs MediaPipe."""
    for d in [work / "visual", reuse, mit_measurement_dir(video)]:
        if d and (d / "timeline.json").exists() and (d / "measurements.jsonl").exists():
            tl = json.loads((d / "timeline.json").read_text())
            if tl.get("source_sha256") in (None, video_sha):
                rows = [json.loads(x) for x in (d / "measurements.jsonl").read_text().splitlines() if x.strip()]
                log(f"visual: reusing {len(rows)} measured frames from {d}")
                return rows, tl
    from video_pipeline import run  # MediaPipe, OpenCV, onnxruntime, sklearn
    log(f"visual: measuring {video.name} at {sample_fps:g} fps (this takes a few seconds per minute of video)")
    tl = run(video, MODELS / "face_landmarker.task", CLASSIFIERS, work / "visual", sample_fps, 2.0, None,
             MODELS / "mobileone_s0_gaze.onnx")
    rows = [json.loads(x) for x in (work / "visual/measurements.jsonl").read_text().splitlines() if x.strip()]
    return rows, tl


def relative_track(rows, raw_tl, calibration_seconds: float):
    from relative_events import analyze
    timeline, evaluated = analyze(rows, raw_tl["sample_fps"], raw_tl["analyzed_seconds"], calibration_seconds)
    return VisualTrack.from_timeline(timeline, evaluated), timeline


# ------------------------------------------------------------------ ASR

def asr_words(video: Path, work: Path, model_dir: Path, reuse: Path | None, stem: str) -> list[Word]:
    candidates = [work / "asr_words.json", reuse, ROOT / "data/processed/fusion/asr" / f"{stem}.json"]
    for f in candidates:
        if f and f.exists():
            words = json.loads(f.read_text())["words"]
            log(f"asr: reusing {len(words)} words from {f}")
            return [Word(w["text"], w["start"], w["end"]) for w in words]
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("transcript has no word timestamps and faster-whisper is not installed: "
                         "`uv pip install --python .venv-video/bin/python faster-whisper`, or pass --asr-words")
    if not model_dir.exists():
        raise SystemExit(f"faster-whisper model not found at {model_dir}; pass --asr-model")
    log(f"asr: transcribing with {model_dir.name}")
    model = WhisperModel(str(model_dir), device="cpu", compute_type="int8")
    # faster-whisper decodes the video's audio track itself (PyAV), so ffmpeg is not required.
    # The filler-laden prompt nudges Whisper to keep "um/uh", which it otherwise tends to drop.
    segments, info = model.transcribe(str(video), language="en", word_timestamps=True, vad_filter=True,
                                      beam_size=1, condition_on_previous_text=False,
                                      initial_prompt=FILLER_PROMPT)
    words = [{"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
             for s in segments for w in (s.words or [])]
    work.mkdir(parents=True, exist_ok=True)
    (work / "asr_words.json").write_text(json.dumps({"model": model_dir.name, "duration_s": info.duration,
                                                      "words": words}))
    return [Word(w["text"], w["start"], w["end"]) for w in words]


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video", type=Path)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--transcript", help="speaker-labelled transcript: path (.txt/.json) or mit:<stem>")
    src.add_argument("--questions", type=Path,
                     help="questions read aloud in the recording (one per line); answers = speech between them")
    p.add_argument("--interviewer-name", action="append", default=[], help="speaker name(s) of the interviewer")
    p.add_argument("--recording-id")
    p.add_argument("--out", type=Path)
    p.add_argument("--work-dir", type=Path)
    p.add_argument("--sample-fps", type=float, default=2.0)
    p.add_argument("--calibration-seconds", type=float, default=30.0)
    p.add_argument("--min-latency", type=float, default=2.0)
    p.add_argument("--look-window", type=float, default=3.0)
    p.add_argument("--asr-model", type=Path, default=DEFAULT_ASR)
    p.add_argument("--asr-words", type=Path, help="reuse a words JSON ({'words': [{text,start,end}]})")
    p.add_argument("--visual-dir", type=Path, help="reuse video_pipeline output (measurements.jsonl + timeline.json)")
    p.add_argument("--no-video", action="store_true", help="skip visual measurement (look_away becomes unmeasurable)")
    p.add_argument("--brief", action="store_true", help="GPT reviewer briefs for flagged answers (needs .env key)")
    p.add_argument("--llm-model", default="openai/gpt-4o-mini")
    p.add_argument("--include-text", action="store_true", help="include interviewer question text in the JSON")
    args = p.parse_args(argv)

    video = args.video.resolve()
    if not video.exists():
        raise SystemExit(f"video not found: {video}")
    rec = args.recording_id or video.stem
    work = args.work_dir or ROOT / "data/processed/analyze" / rec
    out = args.out or work / "analysis.json"
    started = time.time()

    video_sha = sha256(video)
    located = None
    if args.questions:
        questions = load_questions(args.questions)
        all_words = asr_words(video, work, args.asr_model, args.asr_words, video.stem)
        turns, located = locate_questions(questions, all_words)
        found = sum(q.found for q in located)
        log(f"questions: found {found}/{len(located)} in the speech")
        for q in located:
            where = f"at {q.start:.1f}-{q.end:.1f} s" if q.found else "NOT FOUND (skipped)"
            log(f"  Q{q.index + 1} {where} (match {q.match_ratio:.2f}): {q.question[:60]}")
        if not found:
            raise SystemExit("none of the questions were found in the speech; check the questions file")
        words = None  # turns already carry ASR word timings
    else:
        turns = get_turns(args.transcript, args.interviewer_name)
        log(f"transcript: {len(turns)} speaker turns")

    track, rel_tl = None, None
    if not args.no_video:
        rows, raw_tl = raw_measurements(video, work, video_sha, args.sample_fps, args.visual_dir)
        track, rel_tl = relative_track(rows, raw_tl, args.calibration_seconds)
        log(f"visual: {len(track.events)} look-away events after the {args.calibration_seconds:g} s baseline")

    if not args.questions:
        words = asr_words(video, work, args.asr_model, args.asr_words, video.stem) if needs_asr(turns) else None

    brief_client = None
    if args.brief:
        from interview_integrity.llm import CachedClient, OpenRouterClient, load_dotenv
        for env in (ROOT / ".env", ROOT.parent / "ai-interview-integrity-capstone" / ".env"):
            load_dotenv(env)
        brief_client = CachedClient(OpenRouterClient(), ROOT / "data/processed/fusion/llm_cache.jsonl")

    cfg = FollowupConfig(min_latency_s=args.min_latency, look_window_into_answer_s=args.look_window)
    payload = analyze_recording(
        rec, turns, track, asr_words=words, cfg=cfg, timeline=rel_tl, brief_client=brief_client,
        brief_model=args.llm_model, include_text=args.include_text,
        source={"video_filename": video.name, "video_sha256": video_sha,
                "transcript": (f"questions:{args.questions.name}" if args.questions else
                               args.transcript if args.transcript.startswith("mit:") else Path(args.transcript).name),
                "sample_fps": args.sample_fps},
    )
    if located is not None:
        payload["timing_source"] = "question_list"
        payload["questions_located"] = [
            {"index": q.index + 1, "question": q.question, "found": q.found, "match_ratio": q.match_ratio,
             "start": q.start, "end": q.end} for q in located]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    log(f"done in {time.time() - started:.0f} s: {payload['status_counts']} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
