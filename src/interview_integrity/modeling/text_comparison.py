"""Frozen-input, offline comparison of HC3, MAGE and SuperAnnotate.

Diagnostic only: no ASR, training, thresholds, fusion, verdicts or population metrics.
Publisher-specific preprocessing and deployment thresholds are not reproduced;
all three receive the same unedited candidate-answer text. Full tokens, no truncation.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import re
import time

from .._fs import atomic_write_text
from ..transcription.sidecar import SidecarTranscriber
from .transcript_baseline import HC3Detector, MIN_WORDS, ROOT, sha256, word_count

MODELS = {
    "hc3": {"repo": "Hello-SimpleAI/chatgpt-detector-roberta",
            "revision": "d2b342c61775d5dd0221808a79983ed3b86ffd86",
            "weight": "pytorch_model.bin", "ai_index": 1, "score_type": "uncalibrated_softmax"},
    "mage": {"repo": "yaful/MAGE", "revision": "0d82ca0fdf6ebef5babb813cc11bd8eb2552c846",
             "weight": "pytorch_model.bin", "ai_index": 0, "score_type": "uncalibrated_softmax",
             "semantics_source": "https://github.com/yafuly/MAGE/blob/6d11f851184b9f04166f952ddc1f47727f36710f/deployment/utils.py",
             "publisher_reference_ai_logit_threshold": 3.08583984375},
    "superannotate": {"repo": "SuperAnnotate/ai-detector",
                      "revision": "74b2b8580915c202607c09f64f8170eaa87a6a14",
                      "weight": "model.safetensors", "ai_index": 0,
                      "score_type": "uncalibrated_sigmoid",
                      "semantics_source": "https://github.com/superannotateai/generated_text_detector/blob/dbd6317968d144291192a2baf33e11df4e6cdf65/generated_text_detector/utils/model/roberta_classifier.py"},
}
BASE_REPO = "FacebookAI/roberta-large"
BASE_REVISION = "722cf37b1afa9454edce342e7895e588b6ff1d59"
COMMON_MAX_TOKENS = 512
MODEL_FILES = ["config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
               "merges.txt", "vocab.json", "README.md", "LICENSE"]
WARNINGS = [
    "Previously inspected diagnostic samples, not a blind independent test set.",
    "Synthetic colloquial and standard answers are BOTH AI-generated, not human negatives.",
    "Recorded spontaneous provenance is user-reported; reading provenance is unverified.",
    "Scores have different training/calibration and are NOT interchangeable AI-use probabilities.",
    "Identical raw-text HF checkpoint comparison; publisher cleanup/thresholds are not applied.",
    "No threshold selection, model winner, accuracy/FPR estimate, hiring verdict or fusion.",
]


def validate_config(name: str, config: dict) -> None:
    if name == "mage":
        if (config.get("model_type") != "longformer" or
                {int(k): int(v) for k, v in config.get("id2label", {}).items()} != {0: 0, 1: 1}):
            raise ValueError("Unexpected MAGE architecture/labels; class 0=machine, 1=human")
    elif name == "superannotate":
        if (config.get("pretrain_checkpoint") != BASE_REPO or config.get("num_labels") != 1
                or config.get("id2label") != {"0": "GENERATED"}
                or config.get("classifier_dropout") != 0.1):
            raise ValueError("Unexpected SuperAnnotate architecture/GENERATED label")
    else:
        raise ValueError("Unknown config type")


def validated_scores(scores: dict) -> dict:
    if not isinstance(scores, dict) or not {"ai_text_score", "human_score"}.issubset(scores):
        raise ValueError("Incomplete scores")
    values = [scores["ai_text_score"], scores["human_score"]]
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            or not 0 <= v <= 1 for v in values) or not math.isclose(sum(values), 1, abs_tol=1e-5)):
        raise ValueError("Invalid scores")
    logits = scores.get("raw_logits")
    if logits is not None and (not isinstance(logits, list) or not logits or
                               any(isinstance(v, bool) or not isinstance(v, (int, float))
                                   or not math.isfinite(v) for v in logits)):
        raise ValueError("Invalid raw logits")
    return scores


def _snapshot(name: str, cache_root: Path) -> Path:
    from huggingface_hub import snapshot_download
    spec = MODELS[name]
    return Path(snapshot_download(spec["repo"], revision=spec["revision"],
                                 cache_dir=str(cache_root / name), local_files_only=True, token=False,
                                 allow_patterns=MODEL_FILES + [spec["weight"]]))


def _superannotate_model(config: dict, base_config: dict, weights: Path):
    """Inference-only reconstruction of the publisher's CLS -> dropout -> linear head.

    No copied training/service package or remote code is executed. Encoder initialized
    from a pinned LOCAL config; complete safetensors checkpoint is loaded strictly.
    Architecture attribution: SuperAnnotate generated_text_detector, Apache-2.0 source.
    Model weights carry their separate SAIPL licence; local research only here.
    """
    import torch
    from safetensors.torch import load_file
    from transformers import RobertaConfig, RobertaModel

    class EncoderWithLinearHead(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.roberta = RobertaModel(RobertaConfig.from_dict(base_config), add_pooling_layer=False)
            self.dropout = torch.nn.Dropout(config["classifier_dropout"])
            self.dense = torch.nn.Linear(base_config["hidden_size"], 1)

        def forward(self, **encoded):
            cls = self.roberta(**encoded).last_hidden_state[:, 0, :]
            return self.dense(self.dropout(cls))

    model = EncoderWithLinearHead()
    state = load_file(str(weights), device="cpu")
    model.load_state_dict(state, strict=True)  # NEVER ignore missing/unused classifier weights.
    return model.to("cpu").eval()


class Candidate:
    def __init__(self, name: str, cache_root: Path):
        if name not in MODELS:
            raise ValueError("Unknown model")
        self.name = name
        self.hc3 = None
        if name == "hc3":
            self.hc3 = HC3Detector(cache_root / name)
            return
        from transformers import AutoTokenizer
        path = _snapshot(name, cache_root)
        self.config = json.loads((path / "config.json").read_text())
        validate_config(name, self.config)
        self.tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True,
                                                      trust_remote_code=False, token=False)
        if name == "mage":
            from transformers import AutoModelForSequenceClassification
            self.model = AutoModelForSequenceClassification.from_pretrained(
                str(path), local_files_only=True, trust_remote_code=False,
                use_safetensors=False, weights_only=True, token=False,
            ).to("cpu").eval()
            validate_config(name, self.model.config.to_dict())
        else:
            from huggingface_hub import snapshot_download
            base = Path(snapshot_download(BASE_REPO, revision=BASE_REVISION,
                                          cache_dir=str(cache_root / "superannotate-base-config"),
                                          local_files_only=True, token=False, allow_patterns=["config.json"]))
            base_config = json.loads((base / "config.json").read_text())
            if base_config.get("model_type") != "roberta" or base_config.get("hidden_size") != 1024:
                raise ValueError("Unexpected encoder config")
            self.model = _superannotate_model(self.config, base_config, path / "model.safetensors")

    def token_count(self, text: str) -> int:
        if self.hc3 is not None:
            return self.hc3.token_count(text)
        return len(self.tokenizer.encode(text, add_special_tokens=True, truncation=False))

    def score(self, text: str) -> dict:
        if self.token_count(text) > COMMON_MAX_TOKENS:
            raise ValueError("No truncation: answer exceeds common token capacity")
        if self.hc3 is not None:
            return self.hc3.score(text)
        import torch
        encoded = self.tokenizer(text, return_tensors="pt", truncation=False)
        with torch.inference_mode():
            if self.name == "mage":
                logits = self.model(**encoded).logits[0]
                probs = torch.softmax(logits, dim=-1).tolist()
                return {"ai_text_score": float(probs[0]), "human_score": float(probs[1]),
                        "raw_logits": logits.tolist()}
            logits = self.model(**encoded)[0]
            if logits.numel() != 1:
                raise ValueError("Expected a single GENERATED logit")
            score = float(torch.sigmoid(logits).item())
            return {"ai_text_score": score, "human_score": 1 - score, "raw_logits": logits.tolist()}


def load_samples(manifest: Path) -> list[dict]:
    data = json.loads(manifest.read_text())
    if (not isinstance(data, dict) or data.get("candidate_only") is not True
            or not isinstance(data.get("samples"), list) or not data["samples"]):
        raise ValueError("Manifest must confirm candidate-only and provide samples")
    samples, seen = [], set()
    for item in data["samples"]:
        if (not isinstance(item, dict) or not isinstance(item.get("path"), str)
                or not item["path"] or not isinstance(item.get("provenance", {}), dict)):
            raise ValueError("Invalid sample path/provenance")
        sample_id = item.get("id", "")
        if not isinstance(sample_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", sample_id) or sample_id in seen:
            raise ValueError("Invalid/duplicate sample ID")
        seen.add(sample_id)
        path = (manifest.parent / item["path"]).resolve()
        transcript = SidecarTranscriber(path).transcribe()
        samples.append({"id": sample_id, "path": str(path), "source_sha256": sha256(path),
                        "text": transcript.text, "language": transcript.language or item.get("language"),
                        "provenance": item.get("provenance", {}), "word_count": word_count(transcript.text),
                        "text_sha256": hashlib.sha256(transcript.text.encode()).hexdigest()})
    return samples


def runtime_versions() -> dict:
    result = {}
    for name in ("transformers", "torch", "safetensors", "huggingface_hub"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


def compare(manifest: Path, out: Path, *, model_names: list[str],
            cache_root: Path, factory=Candidate) -> dict:
    if out.exists():
        raise ValueError("Output already exists; choose a new private directory")
    if not model_names or len(set(model_names)) != len(model_names) or any(n not in MODELS for n in model_names):
        raise ValueError("Invalid/duplicate model names")
    # Freeze all inputs/provenance before loading or scoring any candidate.
    samples = load_samples(manifest)
    result = {"purpose": "frozen-input diagnostic, not independent validation", "models": {n: MODELS[n] for n in model_names},
              "samples": [{k: v for k, v in s.items() if k != "text"} for s in samples],
              "manifest_sha256": sha256(manifest), "rows": [], "model_errors": {},
              "common_max_tokens": COMMON_MAX_TOKENS, "min_words": MIN_WORDS,
              "preprocessing": "raw_unedited_transcript_text", "asr_rerun": False,
              "llm_cleanup": False, "retrained": False, "threshold_selected": False,
              "selected_model": None, "accuracy_estimated": False, "confidence": None,
              "verdict": None, "sends_content_externally": False, "warnings": WARNINGS,
              "integrity_status": "pending",
              "runtime_versions": runtime_versions()}
    out.mkdir(parents=True, exist_ok=False)
    for sample in samples:
        atomic_write_text(out / "inputs" / (sample["id"] + ".txt"), sample["text"] + "\n")
    for name in model_names:
        candidate = None
        loaded = time.monotonic()
        try:
            candidate = factory(name, cache_root)
        except (OSError, ImportError, RuntimeError, ValueError) as exc:
            result["model_errors"][name] = str(exc)
        load_seconds = round(time.monotonic() - loaded, 3)
        for sample in samples:
            row = {"model": name, "sample": sample["id"], "source_sha256": sample["source_sha256"],
                   "text_sha256": sample["text_sha256"], "word_count": sample["word_count"],
                   "provenance": sample["provenance"], "token_count": None,
                   "status": "not_evaluated", "ai_text_score": None, "human_score": None,
                   "score_type": MODELS[name]["score_type"], "model_load_seconds": load_seconds,
                   "text_truncated": False}
            started = time.monotonic()
            if name in result["model_errors"]:
                row["status"] = "model_error"
            elif sample["language"] != "en":
                row["status"] = "unsupported_or_unknown_language"
            elif sample["word_count"] < MIN_WORDS:
                row["status"] = "insufficient_text"
            else:
                try:
                    count = candidate.token_count(sample["text"])
                    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
                        raise ValueError("Invalid token count")
                    row["token_count"] = count
                    if count > COMMON_MAX_TOKENS:
                        row["status"] = "answer_exceeds_common_capacity"
                    else:
                        row.update(validated_scores(candidate.score(sample["text"])))
                        row["status"] = "scored_exploratory"
                except (OSError, ImportError, RuntimeError, ValueError) as exc:
                    row["status"] = "inference_error"
                    row["error"] = str(exc)
            row["inference_seconds"] = round(time.monotonic() - started, 3)
            result["rows"].append(row)
        del candidate
        gc.collect()
        atomic_write_text(out / "comparison.json", json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    try:
        unchanged = (sha256(manifest) == result["manifest_sha256"]
                     and all(sha256(Path(s["path"])) == s["source_sha256"] for s in samples))
    except OSError:
        unchanged = False
    result["integrity_status"] = "verified" if unchanged else "failed"
    atomic_write_text(out / "comparison.json", json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    if not unchanged:
        raise ValueError("Source/manifest changed during comparison; do not interpret this run")
    lines = ["# Frozen-transcript model comparison", "", *["- " + w for w in WARNINGS], "",
             "Scores increase toward each checkpoint's AI/generated class, but are not calibrated or interchangeable.", "",
             "| Sample | Model | AI-text score | Tokens | Status |", "| --- | --- | --- | --- | --- |"]
    for sample in samples:
        for row in (r for r in result["rows"] if r["sample"] == sample["id"]):
            score = "n/a" if row["ai_text_score"] is None else f"{row['ai_text_score']:.6f}"
            lines.append(f"| {sample['id']} | {row['model']} | {score} | {row['token_count']} | {row['status']} |")
    lines.extend(["", "No winner or threshold selected. All source hashes verified unchanged after inference.",
                  "Raw logits are retained for MAGE/SuperAnnotate. MAGE's publisher uses a raw-logit",
                  "threshold rather than the softmax score; that threshold is not applied here.",
                  "SuperAnnotate uses a single GENERATED logit with sigmoid, not two-class softmax.",
                  "All transcripts, provenance and detailed results are private; do not commit them.", ""])
    atomic_write_text(out / "report.md", "\n".join(lines))
    return result


def download_models(names: list[str], cache_root: Path) -> None:
    from huggingface_hub import snapshot_download
    for name in names:
        spec = MODELS[name]
        snapshot_download(spec["repo"], revision=spec["revision"], cache_dir=str(cache_root / name),
                          token=False, allow_patterns=MODEL_FILES + [spec["weight"]])
    if "superannotate" in names:
        snapshot_download(BASE_REPO, revision=BASE_REVISION,
                          cache_dir=str(cache_root / "superannotate-base-config"), token=False,
                          allow_patterns=["config.json"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download", help="Explicit public-weight download only")
    run = sub.add_parser("run", help="Offline frozen-input comparison")
    for command in (download, run):
        command.add_argument("--models", nargs="+", choices=list(MODELS), default=list(MODELS))
        command.add_argument("--cache-root", type=Path, default=ROOT / ".cache/models")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "download":
            download_models(args.models, args.cache_root)
            print("Pinned public weights cached; no interview data uploaded.")
            return
        if not args.out_dir.resolve().is_relative_to(ROOT / "data/processed"):
            raise ValueError("Private output must stay under ignored data/processed")
        result = compare(args.manifest, args.out_dir, model_names=args.models, cache_root=args.cache_root)
        print(json.dumps([{k: r[k] for k in ("sample", "model", "status", "ai_text_score")} for r in result["rows"]], indent=2))
        print(f"Private report: {args.out_dir / 'report.md'}")
        if result["model_errors"] or any(r["status"] == "inference_error" for r in result["rows"]):
            parser.exit(2, "Some models failed; inspect the private JSON, no missing score is treated as zero.\n")
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        parser.exit(2, f"transcript-compare: {exc}\n")


if __name__ == "__main__":
    main()
