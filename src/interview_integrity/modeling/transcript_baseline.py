"""Local ASR -> HC3 text-detector smoke test, not an interview AI-use verdict.

No training, remote inference, LLM cleanup, text truncation, or audio-score fusion.
Heavy dependencies are lazy; model downloads require a separate explicit command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Any

from .._fs import atomic_write_text
from ..audio.quality import validate_audio
from ..media import MediaError, ffprobe, first_stream, run_ffmpeg
from ..transcription.base import Transcript
from ..transcription.sidecar import SidecarTranscriber

MODEL_ID = "Hello-SimpleAI/chatgpt-detector-roberta"
MODEL_REVISION = "d2b342c61775d5dd0221808a79983ed3b86ffd86"
MODEL_FILES = ["config.json", "pytorch_model.bin", "tokenizer.json", "tokenizer_config.json",
               "special_tokens_map.json", "merges.txt", "vocab.json", "README.md"]
MODEL_LABELS = {0: "Human", 1: "ChatGPT"}
MAX_TOKENS = 512
MIN_WORDS = 50  # Engineering guard, NOT a validated scientific reliability threshold.
ROOT = Path(__file__).resolve().parents[3]
WARNINGS = [
    "Exploratory written-Q&A detector; interview ASR transcripts are out of domain.",
    "Scores are uncalibrated model outputs, NOT probabilities of AI assistance or cheating.",
    "Low scores do not establish independent authorship; high scores are not proof of AI use.",
    "ASR errors, short answers, paraphrasing, newer LLMs and non-native English can change scores.",
    "No automated hiring decision, audio/text fusion, retraining or external data upload.",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*\b", text))


def validate_labels(labels: dict) -> None:
    if {int(key): value for key, value in labels.items()} != MODEL_LABELS:
        raise ValueError("HC3 label mapping differs from verified Human=0, ChatGPT=1")


class HC3Detector:
    """Pinned, local-only inference; no arbitrary Hub code or unrestricted pickle load."""

    def __init__(self, cache_dir: str | Path):
        from transformers import AutoTokenizer
        self.cache_dir = str(cache_dir)
        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, cache_dir=self.cache_dir,
            local_files_only=True, trust_remote_code=False, token=False,
        )
        self.model = None

    def token_count(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=True, truncation=False))

    def score(self, text: str) -> dict[str, float]:
        import torch
        if self.token_count(text) > MAX_TOKENS:
            raise ValueError("Answer exceeds HC3 capacity; silent truncation is prohibited")
        if self.model is None:
            from transformers import AutoModelForSequenceClassification
            self.model = AutoModelForSequenceClassification.from_pretrained(
                MODEL_ID, revision=MODEL_REVISION, cache_dir=self.cache_dir,
                local_files_only=True, trust_remote_code=False, token=False,
                use_safetensors=False, weights_only=True,
            ).to("cpu").eval()
            validate_labels(self.model.config.id2label)
        encoded = self.tokenizer(text, return_tensors="pt", truncation=False)
        with torch.inference_mode():
            scores = torch.softmax(self.model(**encoded).logits, dim=-1)[0].tolist()
        if len(scores) != 2:
            raise ValueError("HC3 must return two label scores")
        return {"human_score": float(scores[0]), "ai_text_score": float(scores[1])}


def assess_transcript(transcript: Transcript, *, detector: Any = None,
                      cache_dir: str | Path = ".cache/models/hc3",
                      declared_language: str | None = None,
                      quality_flags: list[str] | None = None) -> dict:
    """Score an entire candidate answer. No source labels or filenames enter the model."""
    text = transcript.text
    language = transcript.language or declared_language
    flags = list(quality_flags or [])
    result = {
        "target": "written_Human_vs_ChatGPT_style_baseline",
        "status": "not_evaluated", "language": language,
        "word_count": word_count(text), "token_count": None,
        "human_score": None, "ai_text_score": None,
        "score_type": "uncalibrated_softmax", "confidence": None, "verdict": None,
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "min_words": MIN_WORDS, "max_tokens": MAX_TOKENS,
        "quality_flags": flags, "warnings": list(WARNINGS),
        "text_truncated": False, "llm_cleanup_used": False,
    }
    if not text.strip():
        result["status"] = "empty_transcript"
    elif language != "en":
        result["status"] = "unsupported_or_unknown_language"
    elif flags:
        result["status"] = "audio_quality_review_required"
    elif result["word_count"] < MIN_WORDS:
        result["status"] = "insufficient_text"
    else:
        detector = detector if detector is not None else HC3Detector(cache_dir)
        count = detector.token_count(text)
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError("Invalid token count")
        result["token_count"] = count
        if count > MAX_TOKENS:
            result["status"] = "answer_exceeds_model_capacity"
        else:
            scores = detector.score(text)
            if set(scores) != {"human_score", "ai_text_score"}:
                raise ValueError("Incomplete detector scores")
            if any(isinstance(v, bool) or not math.isfinite(float(v)) or not 0 <= v <= 1
                   for v in scores.values()) or not math.isclose(sum(scores.values()), 1, abs_tol=1e-5):
                raise ValueError("Invalid detector scores")
            result.update(scores)
            result["status"] = "scored_exploratory"
    return result


def validate_inputs(source: Path, out: Path, *, candidate_only: bool,
                    start: float = 0, end: float | None = None) -> None:
    if not candidate_only:
        raise ValueError("Confirm candidate-only audio/text; mixed interviewer audio is not supported")
    if not source.is_file():
        raise FileNotFoundError(source)
    if out.exists():
        raise ValueError("Output already exists; choose a new private directory")
    if (not math.isfinite(start) or start < 0 or
            (end is not None and (not math.isfinite(end) or end <= start))):
        raise ValueError("Invalid candidate answer interval")


def save_report(out: Path, transcript: Transcript, result: dict) -> None:
    atomic_write_text(out / "transcript.json", json.dumps(transcript.to_dict(), indent=2, ensure_ascii=False) + "\n")
    atomic_write_text(out / "transcript.txt", transcript.text + "\n")
    atomic_write_text(out / "result.json", json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    # Fence arbitrary transcript content rather than interpreting it as Markdown.
    fence = "`" * max(3, 1 + max((len(m.group()) for m in re.finditer(r"`+", transcript.text)), default=0))
    lines = ["# Local transcript-detector smoke test", "", f"Status: {result['status']}.",
             f"Language: {result['language'] or 'unknown'}; words: {result['word_count']}; "
             f"tokens: {result['token_count'] or 'not evaluated'}.", "",
             f"AI-text model score: {result['ai_text_score']} (uncalibrated, NOT cheating probability).",
             "No human/AI verdict is issued. No recording-level accuracy is estimated.", "",
             "## Limitations", "", *["- " + item for item in result["warnings"]], "",
             "The 50-word guard is an engineering setting, not a validated reliability cutoff.",
             "This report and transcript contain private content. Do not commit them.", "",
             "## Unedited transcript", "", fence, transcript.text, fence, ""]
    atomic_write_text(out / "report.md", "\n".join(lines))


def evaluate_file(source: str | Path, out: str | Path, *, input_kind: str,
                  candidate_only: bool, detector: Any = None, transcriber: Any = None,
                  cache_dir: str | Path = ".cache/models/hc3",
                  asr_cache: str | Path = ".cache/models/faster-whisper",
                  declared_language: str | None = None,
                  start: float = 0, end: float | None = None) -> dict:
    source, out = Path(source), Path(out)
    validate_inputs(source, out, candidate_only=candidate_only, start=start, end=end)
    if input_kind not in {"audio", "transcript"}:
        raise ValueError("Input must be audio or transcript")
    if input_kind == "transcript" and (start != 0 or end is not None):
        raise ValueError("For sidecar input, provide an already isolated candidate answer")
    source_hash = sha256(source)
    flags: list[str] = []
    asr_seconds = 0.0
    asr_details = None
    if input_kind == "audio":
        probe = ffprobe(source)
        if first_stream(probe, "audio") is None:
            raise ValueError("Input has no audio stream")
        duration = float(probe["format"]["duration"])
        if not math.isfinite(duration) or duration <= 0 or start >= duration or (end is not None and end > duration):
            raise ValueError("Candidate answer interval is outside the recording")
        out.mkdir(parents=True, exist_ok=False)
        normalized = out / "normalized.wav"
        args = ["-n", "-i", str(source), "-ss", str(start)]
        if end is not None:
            args.extend(["-t", str(end - start)])
        run_ffmpeg([*args, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(normalized)])
        quality = validate_audio(normalized)
        flags = quality.flags
        if flags:
            # Do not give silence, clipping or uncertain channel quality a misleading score.
            transcript = Transcript([], provider="not_run:audio_quality_guard")
        else:
            if transcriber is None:
                from ..transcription.adapters.faster_whisper import FasterWhisperTranscriber
                transcriber = FasterWhisperTranscriber(
                    "small", device="cpu", compute_type="int8", language=None,
                    vad_filter=True, initial_prompt=None, word_timestamps=True,
                    download_root=str(asr_cache), allow_download=False,
                )
            asr_details = transcriber.describe() if hasattr(transcriber, "describe") else {"name": "injected_test_transcriber"}
            asr_started = time.monotonic()
            transcript = transcriber.transcribe(normalized)
            asr_seconds = time.monotonic() - asr_started
    else:
        transcript = SidecarTranscriber(source).transcribe()
        out.mkdir(parents=True, exist_ok=False)
    scoring_started = time.monotonic()
    result = assess_transcript(transcript, detector=detector, cache_dir=cache_dir,
                               declared_language=(declared_language if input_kind == "transcript" else None),
                               quality_flags=flags)
    if flags:
        result["status"] = "audio_quality_review_required"
    result.update({"source_sha256": source_hash, "input_kind": input_kind,
                   "candidate_only_confirmed_by_user": candidate_only,
                   "audio_interval": {"start": start, "end": end or duration} if input_kind == "audio" else None,
                   "transcript_sha256": hashlib.sha256(transcript.text.encode()).hexdigest(),
                   "transcript_provider": transcript.provider, "asr_details": asr_details,
                   "asr_seconds": round(asr_seconds, 3),
                   "scoring_seconds": round(time.monotonic() - scoring_started, 3),
                   "ground_truth": None, "accuracy_estimated": False,
                   "retrained": False, "sends_content_externally": False})
    save_report(out, transcript, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="Explicitly download pinned public weights only")
    download.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/models/hc3")
    predict = commands.add_parser("predict", help="Offline local candidate-answer inference")
    source = predict.add_mutually_exclusive_group(required=True)
    source.add_argument("--audio", type=Path)
    source.add_argument("--transcript", type=Path, help="Candidate-only .txt or project/Whisper .json")
    predict.add_argument("--candidate-only", action="store_true", required=True,
                         help="Confirm the input/interval contains only the candidate answer")
    predict.add_argument("--out-dir", type=Path, required=True, help="NEW directory under ignored data/processed/")
    predict.add_argument("--language", choices=["en"], help="Declare English for an untagged sidecar; audio language is detected")
    predict.add_argument("--start", type=float, default=0)
    predict.add_argument("--end", type=float)
    predict.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/models/hc3")
    predict.add_argument("--asr-cache", type=Path, default=ROOT / ".cache/models/faster-whisper")
    args = parser.parse_args()
    try:
        if args.command == "download":
            from huggingface_hub import snapshot_download
            path = snapshot_download(MODEL_ID, revision=MODEL_REVISION, cache_dir=str(args.cache_dir),
                                     token=False, allow_patterns=MODEL_FILES)
            print(f"Pinned detector cached: {path}")
            return
        out = args.out_dir.resolve()
        if not out.is_relative_to(ROOT / "data/processed"):
            raise ValueError("Private output must stay under this checkout's ignored data/processed directory")
        if args.audio and args.language:
            raise ValueError("--language is for sidecars only; do not force English onto non-English audio")
        result = evaluate_file(
            args.audio or args.transcript, out,
            input_kind="audio" if args.audio else "transcript", candidate_only=args.candidate_only,
            cache_dir=args.cache_dir, asr_cache=args.asr_cache, declared_language=args.language,
            start=args.start, end=args.end,
        )
        print(json.dumps({key: result[key] for key in ("status", "language", "word_count", "ai_text_score", "score_type")}))
        print(f"Private report: {out / 'report.md'}")
    except (ValueError, OSError, ImportError, RuntimeError, MediaError) as exc:
        parser.exit(2, f"transcript-baseline: {exc}\n")


if __name__ == "__main__":
    main()
