"""Private three-condition audio -> ASR -> Fast-DetectGPT diagnostic.

Preparation/ASR and detector inference are separate processes. Metadata labels
never enter the detector. Missing conditions/provenance are explicit, not invented.
No thresholds, probability mapping, accuracy estimate, training or external upload.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import time

from .._fs import atomic_write_text
from ..audio.quality import validate_audio
from ..media import ffprobe, first_stream, run_ffmpeg
from ..transcription.base import Transcript
from ..transcription.sidecar import SidecarTranscriber
from .beemo_benchmark import text_hash, write_json
from .detector_followup import FAST_MODEL, FastCandidate
from .text_comparison import COMMON_MAX_TOKENS, runtime_versions
from .transcript_baseline import MIN_WORDS, ROOT, sha256, word_count

ASR_SETTINGS = {"model_size": "small", "device": "cpu", "compute_type": "int8",
                "language": None, "vad_filter": True, "initial_prompt": None,
                "word_timestamps": True, "beam_size": 5}
PRIMARY = {"human_spontaneous": 0, "human_self_script": 0, "ai_verbatim": 1}
CONDITIONS = set(PRIMARY) | {"unknown", "ai_personalized", "ai_text_control"}
PROVENANCE = {"unknown", "self_reported", "protocol_verified", "known_generated"}
WARNINGS = [
    "Previously inspected small personal diagnostic; not blind interview validation.",
    "Reading is a delivery style, NOT evidence of AI assistance or answer provenance.",
    "Raw signed discrepancy is not a probability; no threshold or verdict is applied.",
    "Pure-text AI controls bypass ASR and are excluded from the audio pilot cohort.",
    "Unknown/personalized provenance cannot be converted into human negatives.",
    "A single speaker/topic and missing conditions cannot establish accuracy/FPR/AUROC.",
]


def validate_samples(data: dict, root: Path) -> list[dict]:
    if (not isinstance(data, dict) or data.get("purpose") != "verbatim_asr_pilot" or data.get("candidate_only") is not True
            or not isinstance(data.get("samples"), list) or not data["samples"]):
        raise ValueError("Confirm candidate-only pilot with nonempty samples")
    samples, seen = [], set()
    for item in data["samples"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid sample")
        ident = item.get("id")
        if (not isinstance(ident, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", ident)
                or ident in seen or item.get("condition") not in CONDITIONS
                or item.get("provenance_status") not in PROVENANCE
                or item.get("input_kind") not in {"audio", "text"}
                or not isinstance(item.get("path"), str) or not item["path"]
                or item.get("language") != "en"):
            raise ValueError("Invalid/duplicate ID, condition, provenance or input")
        if item["condition"] == "ai_text_control" and item["input_kind"] != "text":
            raise ValueError("Pure-text control cannot be an audio condition")
        if item["input_kind"] == "text" and item["condition"] != "ai_text_control":
            raise ValueError("Text-only examples cannot fill an audio pilot condition")
        if item["condition"] in PRIMARY and item["provenance_status"] not in {"self_reported", "protocol_verified"}:
            raise ValueError("Primary condition needs explicit provenance, never a filename guess")
        if item["condition"] == "ai_text_control" and item["provenance_status"] != "known_generated":
            raise ValueError("AI text control needs known generation provenance")
        if item["condition"] == "unknown" and item["provenance_status"] != "unknown":
            raise ValueError("Unknown condition must retain unknown provenance")
        path = (root / item["path"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        samples.append({**item, "path": str(path), "source_sha256": sha256(path)})
        seen.add(ident)
    return samples


def prepare(inputs: Path, out: Path, asr_cache: Path, *, transcriber=None, progress=None) -> dict:
    if out.exists():
        raise ValueError("Output exists; preserve previous run")
    inputs_hash = sha256(inputs)
    samples = validate_samples(json.loads(inputs.read_text()), inputs.parent)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"purpose": "verbatim_asr_pilot", "candidate_only": True,
                "inputs_file": str(inputs.resolve()), "inputs_sha256": inputs_hash,
                "asr_settings": ASR_SETTINGS, "samples": [], "integrity_status": "pending",
                "accuracy_estimated": False, "threshold_selected": False, "warnings": WARNINGS}
    write_json(out / "manifest.json", manifest)
    for sample in samples:
        started = time.monotonic()
        flags = []
        if sample["input_kind"] == "audio":
            probe = ffprobe(sample["path"])
            if first_stream(probe, "audio") is None:
                raise ValueError("No audio stream")
            duration = float(probe["format"]["duration"])
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("Invalid audio duration")
            normalized = out / sample["id"] / "normalized.wav"
            normalized.parent.mkdir(parents=True, exist_ok=False)
            run_ffmpeg(["-n", "-i", sample["path"], "-vn", "-ac", "1", "-ar", "16000",
                        "-c:a", "pcm_s16le", str(normalized)])
            flags = validate_audio(normalized).flags
            if flags:
                transcript = Transcript([], provider="not_run:audio_quality_guard")
            else:
                if transcriber is None:
                    from ..transcription.adapters.faster_whisper import FasterWhisperTranscriber
                    transcriber = FasterWhisperTranscriber(**ASR_SETTINGS, download_root=str(asr_cache), allow_download=False)
                transcript = transcriber.transcribe(normalized)
        else:
            duration = None
            transcript = SidecarTranscriber(sample["path"]).transcribe()
            transcript.language = sample["language"]
        transcript_path = out / sample["id"] / "transcript.json"
        write_json(transcript_path, transcript.to_dict())
        atomic_write_text(transcript_path.with_suffix(".txt"), transcript.text + "\n")
        manifest["samples"].append({**sample, "transcript_path": str(transcript_path.resolve()),
            "transcript_file_sha256": sha256(transcript_path), "text_sha256": text_hash(transcript.text),
            "language_detected": transcript.language, "word_count": word_count(transcript.text),
            "duration_seconds": duration, "quality_flags": flags,
            "asr_used": sample["input_kind"] == "audio" and not flags,
            "preparation_seconds": time.monotonic() - started})
        write_json(out / "manifest.json", manifest)
        if progress:
            progress(f"Prepared {sample['id']}: {word_count(transcript.text)} words, quality flags {flags}")
    unchanged = sha256(inputs) == inputs_hash and all(sha256(Path(s["path"])) == s["source_sha256"] for s in samples)
    manifest["integrity_status"] = "verified" if unchanged else "failed"
    write_json(out / "manifest.json", manifest)
    if not unchanged:
        raise ValueError("Source/metadata changed during ASR")
    return manifest


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text())
    if (manifest.get("purpose") != "verbatim_asr_pilot" or manifest.get("integrity_status") != "verified"
            or manifest.get("asr_settings") != ASR_SETTINGS or manifest.get("candidate_only") is not True
            or not manifest.get("samples")):
        raise ValueError("Unverified/mismatched pilot manifest")
    inputs = Path(manifest["inputs_file"])
    if sha256(inputs) != manifest["inputs_sha256"]:
        raise ValueError("Input metadata changed after freeze")
    originals = validate_samples(json.loads(inputs.read_text()), inputs.parent)
    if len(originals) != len(manifest["samples"]):
        raise ValueError("Frozen sample count changed")
    for old, sample in zip(originals, manifest["samples"]):
        if any(sample.get(k) != v for k, v in old.items()):
            raise ValueError("Frozen source identity or provenance changed")
        transcript = Transcript.from_dict(json.loads(Path(sample["transcript_path"]).read_text()))
        if (old["source_sha256"] != sample["source_sha256"]
                or sha256(Path(sample["transcript_path"])) != sample["transcript_file_sha256"]
                or text_hash(transcript.text) != sample["text_sha256"]
                or word_count(transcript.text) != sample["word_count"]
                or transcript.language != sample["language_detected"]):
            raise ValueError("Frozen source or transcript changed")
    return manifest


def assess(transcript: Transcript, detector, flags: list[str]) -> dict:
    text = transcript.text
    row = {"status": "not_evaluated", "score": None, "score_type": FAST_MODEL["score_type"],
           "token_count": None, "word_count": word_count(text), "language": transcript.language,
           "confidence": None, "verdict": None, "text_truncated": False}
    if flags:
        row["status"] = "audio_quality_review_required"
    elif not text:
        row["status"] = "empty_transcript"
    elif transcript.language != "en":
        row["status"] = "unsupported_or_unknown_language"
    elif word_count(text) < MIN_WORDS:
        row["status"] = "insufficient_text"
    else:
        count = detector.token_count(text)
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError("Invalid token count")
        row["token_count"] = count
        if count > COMMON_MAX_TOKENS:
            row["status"] = "answer_exceeds_capacity"
        else:
            values = detector.score(text)
            value = values.get("score")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError("Invalid signed statistic")
            row.update(score=value, predicted_tokens=values.get("predicted_tokens"),
                       checkpoint_loading_verified=values.get("checkpoint_loading_verified"), status="scored_exploratory")
    return row


def report(result: dict) -> str:
    lines = ["# Private verbatim-ASR diagnostic", "", *["- " + x for x in WARNINGS], "",
             "Higher raw statistic means more machine-like under this method; NOT a probability or verdict.", "",
             "| Sample | Input | Condition | Provenance | Words | Tokens | Raw statistic | Status |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in result["rows"]:
        lines.append(f"| {row['id']} | {row['input_kind']} | {row['condition']} | {row['provenance_status']} | "
                     f"{row['word_count']} | {row['token_count']} | {row['score']} | {row['status']} |")
    lines += ["", "Missing scored audio conditions: " + ", ".join(result["missing_primary_audio_conditions"]),
              "No accuracy, FPR or AUROC calculated; no threshold chosen. Unknown provenance, where present, remains unknown.",
              "This report is private. Do not commit audio, transcripts, full inputs or per-sample outputs.", ""]
    return "\n".join(lines)


def score(manifest_path: Path, out: Path, cache: Path, device: str, *, factory=FastCandidate, progress=None) -> dict:
    if out.exists():
        raise ValueError("Output exists; preserve previous run")
    before = sha256(manifest_path)
    manifest = load_manifest(manifest_path)
    out.mkdir(parents=True, exist_ok=False)
    result = {"purpose": "verbatim_asr_pilot", "model": {**FAST_MODEL, "device": device},
              "manifest_sha256": before, "asr_settings": manifest["asr_settings"], "rows": [],
              "runtime_versions": runtime_versions(), "integrity_status": "pending", "run_status": "running",
              "accuracy_estimated": False, "threshold_selected": False, "sends_content_externally": False,
              "training": False, "confidence": None, "verdict": None, "warnings": WARNINGS}
    write_json(out / "results.json", result)
    detector = factory(cache, device)
    for sample in manifest["samples"]:
        transcript = Transcript.from_dict(json.loads(Path(sample["transcript_path"]).read_text()))
        started = time.monotonic()
        row = {k: sample[k] for k in ("id", "input_kind", "condition", "provenance_status", "text_sha256", "source_sha256")}
        try:
            row.update(assess(transcript, detector, sample["quality_flags"]))
        except (ValueError, OSError, RuntimeError) as exc:
            row.update(status="inference_error", error=str(exc), score=None, token_count=None,
                       word_count=sample["word_count"], confidence=None, verdict=None)
        row["inference_seconds"] = time.monotonic() - started
        result["rows"].append(row)
        write_json(out / "results.json", result)
        if progress:
            progress(f"Scored {sample['id']}: {row['status']}")
    present = {r["condition"] for r in result["rows"] if r["input_kind"] == "audio"
               and r["status"] == "scored_exploratory" and r["condition"] in PRIMARY}
    result["missing_primary_audio_conditions"] = sorted(set(PRIMARY) - present)
    result["primary_audio_condition_counts"] = dict(Counter(r["condition"] for r in result["rows"]
        if r["input_kind"] == "audio" and r["status"] == "scored_exploratory" and r["condition"] in PRIMARY))
    # Revalidate every source/transcript after inference, not only the manifest.
    load_manifest(manifest_path)
    if sha256(manifest_path) != before:
        raise ValueError("Pilot manifest changed during inference")
    result.update(integrity_status="verified", run_status="complete")
    write_json(out / "results.json", result)
    atomic_write_text(out / "report.md", report(result))
    if any(r["status"] == "inference_error" for r in result["rows"]):
        raise RuntimeError("Inference errors; inspect private results")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="Local same-settings ASR, freeze provenance before scoring")
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--asr-cache", type=Path, default=ROOT / ".cache/models/faster-whisper")
    s = sub.add_parser("score", help="Offline detector only; no ASR rerun")
    s.add_argument("--manifest", type=Path, required=True)
    s.add_argument("--out-dir", type=Path, required=True)
    s.add_argument("--cache", type=Path, default=ROOT / ".cache/models/fast-detect-gpt-neo")
    s.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    args = parser.parse_args()
    try:
        if not args.out_dir.resolve().is_relative_to(ROOT / "data/processed"):
            raise ValueError("Private outputs must stay in ignored data/processed")
        progress = lambda x: print(x, flush=True)
        if args.command == "prepare":
            prepare(args.inputs, args.out_dir, args.asr_cache, progress=progress)
        else:
            score(args.manifest, args.out_dir, args.cache, args.device, progress=progress)
        print(f"Private output: {args.out_dir}")
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"verbatim-pilot: {exc}\n")


if __name__ == "__main__":
    main()
