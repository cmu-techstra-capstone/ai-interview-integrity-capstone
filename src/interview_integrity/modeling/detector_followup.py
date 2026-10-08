"""Offline, fixed-input detector follow-up. Research only; no production scoring.

Publisher cleaning executes only checksum-pinned, reviewed preprocessing definitions
from a local cache. Explicit download is separate from offline inference. Raw
Fast-DetectGPT discrepancy is a ranking statistic, NEVER an AI-use probability.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import gc
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import re
import time

from .._fs import atomic_write_text
from .beemo_benchmark import FIELDS, auroc, bootstrap_auc, load_manifest, text_hash, write_json
from .text_comparison import Candidate, COMMON_MAX_TOKENS, MODELS, runtime_versions, validated_scores
from .transcript_baseline import MIN_WORDS, ROOT, sha256, word_count

SOURCES = {
    "mage": {
        "url": "https://raw.githubusercontent.com/yafuly/MAGE/6d11f851184b9f04166f952ddc1f47727f36710f/deployment/utils.py",
        "sha256": "64791a5c776ad56e2896ffd51c351c806db3cb35bd66194b3b933eba19625cec",
        "definitions": ["MosesPunctNormalizer", "_tokenization_norm", "_clean_text", "_rm_line_break", "preprocess"],
        "entry": "preprocess",
    },
    "superannotate": {
        "url": "https://raw.githubusercontent.com/superannotateai/generated_text_detector/dbd6317968d144291192a2baf33e11df4e6cdf65/generated_text_detector/utils/preprocessing.py",
        "sha256": "7631916d1fc2434a2b5471363310ee3d4b371c249f44177470d71463ce49a9a3",
        "definitions": ["preprocessing_text"], "entry": "preprocessing_text",
    },
}
FAST_MODEL = {
    "repo": "EleutherAI/gpt-neo-2.7B",
    "revision": "e24fa291132763e59f4a5422741b424fb5d59056",
    "sampling_equals_scoring": True, "dtype": "float16", "quantized": False,
    "score_type": "uncalibrated_analytic_sampling_discrepancy",
    "method_source": "https://github.com/baoguangsheng/fast-detect-gpt/blob/971b05202bac2bb504d60c0ac0812fea7a8f7c82/scripts/fast_detect_gpt.py",
    "configuration_note": "Smaller publisher-supported baseline, NOT the recommended Llama3 pair.",
}
FAST_FILES = ["config.json", "model.safetensors", "merges.txt", "vocab.json",
              "tokenizer_config.json", "special_tokens_map.json", "README.md"]
WARNINGS = [
    "Same previously inspected Beemo selection: exploratory follow-up, not a new blind test.",
    "Written text, not interview audio or ASR; training overlap remains unaudited.",
    "Expert-edited AI text remains an AI-assisted positive under the project definition.",
    "Ranking statistics are not calibrated AI-use probabilities or hiring verdicts.",
    "No training, threshold fitting, ensemble, model selection or external text upload.",
    "Report exclusions; compare on the SAME intersection of the original 90 complete groups.",
]


def load_cleanup(name: str, cache: Path):
    """No arbitrary remote code: exact reviewed bytes, selected AST definitions only.

    This is a source parity mechanism, NOT a general-purpose sandbox. The hash pin
    and source review are essential. No publisher service/model/download code runs.
    """
    spec = SOURCES[name]
    path = cache / f"{name}.py"
    if sha256(path) != spec["sha256"]:
        raise ValueError("Publisher source checksum mismatch")
    import re
    namespace = {"re": re}
    if name == "mage":
        from cleantext import clean
        from itertools import chain
        namespace.update(clean=clean, chain=chain)
    else:
        from bs4 import BeautifulSoup
        import markdown
        namespace.update(BeautifulSoup=BeautifulSoup, markdown=markdown)
    tree = ast.parse(path.read_text())
    selected = []
    definitions = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in spec["definitions"]:
            selected.append(node)
            definitions.append(node.name)
        elif name == "superannotate" and isinstance(node, ast.Assign):
            if all(isinstance(t, ast.Name) and t.id in {"URL_PATTERN", "EMAIL_PATTERN", "HOMOGLYPH_MAP"}
                   for t in node.targets):
                selected.append(node)
    if definitions != spec["definitions"]:
        raise ValueError("Unexpected publisher definitions")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace[spec["entry"]]


class PublisherCandidate:
    def __init__(self, name: str, cache: Path, source_cache: Path):
        self.clean = load_cleanup(name, source_cache)
        self.candidate = Candidate(name, cache)

    def prepare_text(self, text: str) -> str:
        return self.clean(text)

    def token_count(self, text: str) -> int:
        return self.candidate.token_count(text)

    def score(self, text: str) -> dict:
        values = validated_scores(self.candidate.score(text))
        # MAGE's publisher uses class-0 raw logit, not a 0.5 softmax rule.
        values["score"] = values["raw_logits"][0] if self.candidate.name == "mage" else values["ai_text_score"]
        return values


def analytic_discrepancy(logits_ref, logits_score, labels) -> float:
    """Fast-DetectGPT analytic criterion, stable float64 reduction on CPU.

    Independently expressed from the cited MIT implementation. Equal vocab/token
    alignment required here, rather than silently dropping vocabulary columns.
    Float64 avoids half-precision cancellation; parity tested against formula.
    """
    import torch
    if (logits_ref.shape != logits_score.shape or logits_score.ndim != 3
            or logits_score.shape[0] != 1 or labels.shape != logits_score.shape[:2]
            or labels.numel() < 1):
        raise ValueError("Mismatched reference/scorer tokens or vocabulary")
    ref = logits_ref.detach().to(device="cpu", dtype=torch.float64)
    score = logits_score.detach().to(device="cpu", dtype=torch.float64)
    labels = labels.to(device="cpu")
    if not torch.isfinite(ref).all() or not torch.isfinite(score).all():
        raise ValueError("Nonfinite model logits")
    logp = torch.log_softmax(score, dim=-1)
    p = torch.softmax(ref, dim=-1)
    observed = logp.gather(-1, labels.unsqueeze(-1)).squeeze(-1)
    mean = (p * logp).sum(-1)
    # E[(X-E[X])^2] is algebraically equivalent to E[X^2]-E[X]^2.
    variance = (p * (logp - mean.unsqueeze(-1)).square()).sum(-1).sum()
    if not torch.isfinite(variance) or variance <= 0:
        raise ValueError("Undefined discrepancy variance")
    value = ((observed.sum() - mean.sum()) / variance.sqrt()).item()
    if not math.isfinite(value):
        raise ValueError("Nonfinite discrepancy")
    return value


class FastCandidate:
    def __init__(self, cache: Path, device: str):
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForCausalLM, AutoTokenizer
        if device not in {"cpu", "mps"}:
            raise ValueError("This local baseline supports explicit cpu or mps only")
        if device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("MPS requested but unavailable; no silent device fallback")
        path = snapshot_download(FAST_MODEL["repo"], revision=FAST_MODEL["revision"],
                                 cache_dir=str(cache), local_files_only=True, token=False,
                                 allow_patterns=FAST_FILES)
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True,
                                                       trust_remote_code=False, token=False)
        self.model, loading = AutoModelForCausalLM.from_pretrained(
            path, local_files_only=True, trust_remote_code=False, token=False,
            use_safetensors=True, dtype=torch.float16, attn_implementation="eager",
            output_loading_info=True,
        )
        missing = list(loading.get("missing_keys", []))
        if "lm_head.weight" in missing and self.model.get_output_embeddings().weight is self.model.get_input_embeddings().weight:
            missing.remove("lm_head.weight")  # Explicit tied head, not a random classifier.
        unexpected = [k for k in loading.get("unexpected_keys", []) if not re.fullmatch(
            r"transformer\.h\.\d+\.attn\.attention\.(masked_bias|bias)", k)]
        if missing or unexpected or loading.get("mismatched_keys") or loading.get("error_msgs"):
            raise ValueError(f"Incomplete GPT-Neo checkpoint loading: {loading}")
        self.model = self.model.to(device).eval()
        self.loading_info = loading
        if self.model.config.model_type != "gpt_neo" or self.model.config.hidden_size != 2560:
            raise ValueError("Unexpected GPT-Neo checkpoint architecture")

    def prepare_text(self, text: str) -> str:
        return text

    def token_count(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=True, truncation=False))

    def score(self, text: str) -> dict:
        import torch
        encoded = self.tokenizer(text, return_tensors="pt", truncation=False,
                                 return_token_type_ids=False).to(self.device)
        if encoded.input_ids.shape[1] > COMMON_MAX_TOKENS:
            raise ValueError("No truncation: input exceeds fixed capacity")
        with torch.inference_mode():
            logits = self.model(**encoded, use_cache=False).logits[:, :-1].to("cpu")
        # One model serves as both sampling and scoring model, as in the author's
        # gpt-neo-2.7B/gpt-neo-2.7B baseline. No unknown generator access needed.
        return {"score": analytic_discrepancy(logits, logits, encoded.input_ids[:, 1:]),
                "predicted_tokens": int(encoded.input_ids.shape[1] - 1),
                "checkpoint_loading_verified": True}


def load_baseline(path: Path, manifest_path: Path, manifest: dict) -> dict:
    baseline = json.loads(path.read_text())
    if (baseline.get("integrity_status") != "verified" or baseline.get("run_status") != "complete"
            or baseline.get("manifest_sha256") != sha256(manifest_path)
            or baseline.get("source_sha256") != manifest["source_sha256"]
            or baseline.get("models") != MODELS or baseline.get("model_errors")):
        raise ValueError("Invalid or mismatched original benchmark")
    expected = {(name, s["id"]): s for name in MODELS for s in manifest["samples"]}
    seen = set()
    for row in baseline["rows"]:
        key = (row["model"], row["id"])
        if key in seen or key not in expected:
            raise ValueError("Duplicate/unknown baseline row")
        sample = expected[key]
        if any(row.get(k) != sample[k] for k in ("text_sha256", "prompt_id", "variant", "label")):
            raise ValueError("Baseline sample identity mismatch")
        if row["status"] == "scored_exploratory":
            validated_scores(row)
        seen.add(key)
    if seen != set(expected):
        raise ValueError("Incomplete original benchmark")
    return baseline


def summarize_followup(result: dict, baseline: dict, manifest: dict) -> dict:
    if result.get("integrity_status") != "verified" or result.get("run_status") != "complete":
        raise ValueError("Refuse incomplete/unverified follow-up")
    old = {(r["model"], r["prompt_id"], r["variant"]): r for r in baseline["rows"]}
    new = {(r["model"], r["prompt_id"], r["variant"]): r for r in result["rows"]}
    prompts = sorted({s["prompt_id"] for s in manifest["samples"]})
    if len(new) != len(result["rows"]) or any((n, p, v) not in new for n in result["models"] for p in prompts for v in FIELDS):
        raise ValueError("Incomplete/duplicate follow-up rows")
    original = [p for p in prompts if all(old[n, p, v]["status"] == "scored_exploratory" for n in MODELS for v in FIELDS)]
    common = [p for p in original if all(new[n, p, v]["status"] == "scored_exploratory" for n in result["models"] for v in FIELDS)]
    arms = {
        "hc3_raw": (old, "hc3", "ai_text_score"),
        "mage_raw_softmax": (old, "mage", "ai_text_score"),
        "mage_raw_logit": (old, "mage", "logit"),
        "superannotate_raw": (old, "superannotate", "ai_text_score"),
    }
    for name in result["models"]:
        arms[name] = (new, name, "score")
        if name == "mage_publisher":
            arms["mage_publisher_softmax"] = (new, name, "ai_text_score")
    summary = {"selected_groups": len(prompts), "original_complete_groups": len(original),
               "matched_groups": len(common), "matched_prompt_ids": common,
               "dropped_original_prompt_ids": sorted(set(original) - set(common)),
               "threshold_selected": False, "confidence": None, "verdict": None, "arms": {}, "coverage": {}}
    for arm, (lookup, name, key) in arms.items():
        scores = {v: [(lookup[name, p, v]["raw_logits"][0] if key == "logit" else lookup[name, p, v][key])
                       for p in common] for v in FIELDS}
        if any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x)
               for values in scores.values() for x in values):
            raise ValueError("Nonfinite matched score")
        summary["arms"][arm] = {v: {"auroc": auroc(scores["human"], scores[v]),
            "bootstrap_95_percentile_interval": bootstrap_auc(scores["human"], scores[v], manifest["seed"])}
            for v in ("ai_original", "ai_expert_edited")} if common else {}
    for name in result["models"]:
        summary["coverage"][name] = {v: dict(Counter(new[name, p, v]["status"] for p in prompts)) for v in FIELDS}
    return summary


def report_followup(summary: dict) -> str:
    lines = ["# Fixed-input detector follow-up", "", *["- " + x for x in WARNINGS], "",
             f"Frozen groups: {summary['selected_groups']}; original complete: {summary['original_complete_groups']}; matched: {summary['matched_groups']}.",
             "All rows below use the SAME matched prompt groups. AUROC is NOT accuracy.", "",
             "| Arm | Original AI AUROC [95% CI] | Expert-edited AI AUROC [95% CI] |",
             "| --- | --- | --- |"]
    for name, metrics in summary["arms"].items():
        cells = []
        for v in ("ai_original", "ai_expert_edited"):
            m = metrics.get(v)
            if not m:
                cells.append("n/a")
            else:
                ci = m["bootstrap_95_percentile_interval"]
                cells.append(f"{m['auroc']:.4f}" + (f" [{ci[0]:.4f}, {ci[1]:.4f}]" if ci else ""))
        lines.append(f"| {name} | {' | '.join(cells)} |")
    lines += ["", "## Full frozen-selection coverage", "", "| Arm | Variant | Status counts |", "| --- | --- | --- |"]
    for name, variants in summary["coverage"].items():
        for v, counts in variants.items():
            lines.append(f"| {name} | {v} | {', '.join(f'{k}: {n}' for k, n in counts.items())} |")
    lines += ["", "Publisher cleaning only, not an exact reproduction of their older training/inference runtime.",
              "MAGE logit and softmax rankings are shown separately; no threshold was tuned.",
              "Fast-DetectGPT, if present, uses the smaller single GPT-Neo configuration, NOT the recommended Llama3 pair.", ""]
    return "\n".join(lines)


def run_followup(manifest_path: Path, baseline_path: Path, out: Path, specs: dict, factory, progress=None) -> dict:
    if out.exists():
        raise ValueError("Output exists; choose a new private directory")
    if not specs:
        raise ValueError("No follow-up arms")
    manifest_hash, baseline_hash = sha256(manifest_path), sha256(baseline_path)
    manifest = load_manifest(manifest_path)
    baseline = load_baseline(baseline_path, manifest_path, manifest)
    out.mkdir(parents=True, exist_ok=False)
    result = {"models": specs, "manifest_sha256": manifest_hash, "baseline_sha256": baseline_hash,
              "runtime_versions": runtime_versions(), "rows": [], "model_errors": {},
              "run_status": "running", "integrity_status": "pending", "warnings": WARNINGS,
              "training": False, "threshold_selected": False, "sends_content_externally": False,
              "confidence": None, "verdict": None}
    for dependency in ("clean-text", "emoji", "ftfy", "Unidecode", "beautifulsoup4", "Markdown"):
        try:
            result["runtime_versions"][dependency] = version(dependency)
        except PackageNotFoundError:
            result["runtime_versions"][dependency] = None
    write_json(out / "results.json", result)
    for name in specs:
        candidate = None
        try:
            candidate = factory(name)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            result["model_errors"][name] = str(exc)
        for index, sample in enumerate(manifest["samples"], 1):
            row = {k: sample[k] for k in ("id", "prompt_id", "variant", "label", "text_sha256", "word_count")}
            row.update(model=name, score=None, status="not_evaluated", text_truncated=False,
                       processed_text_sha256=None, processed_word_count=None, token_count=None)
            started = time.monotonic()
            if candidate is None:
                row["status"] = "model_error"
            elif sample["word_count"] < MIN_WORDS:
                row["status"] = "insufficient_text"
            else:
                try:
                    text = candidate.prepare_text(sample["text"])
                    if not isinstance(text, str):
                        raise ValueError("Non-text preprocessor output")
                    row.update(processed_text_sha256=text_hash(text), processed_word_count=word_count(text))
                    if word_count(text) < MIN_WORDS:
                        row["status"] = "insufficient_text_after_preprocessing"
                    else:
                        count = candidate.token_count(text)
                        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
                            raise ValueError("Invalid token count")
                        row["token_count"] = count
                        if count > COMMON_MAX_TOKENS:
                            row["status"] = "answer_exceeds_common_capacity"
                        else:
                            values = candidate.score(text)
                            score = values.get("score")
                            if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
                                raise ValueError("Invalid follow-up statistic")
                            row.update(values, status="scored_exploratory")
                except (ImportError, OSError, RuntimeError, ValueError) as exc:
                    row.update(status="inference_error", error=str(exc))
            row["inference_seconds"] = time.monotonic() - started
            result["rows"].append(row)
            if index % 20 == 0 or index == len(manifest["samples"]):
                write_json(out / "results.json", result)
                if progress:
                    progress(f"{name}: {index}/{len(manifest['samples'])} processed, including abstentions")
        del candidate
        gc.collect()
    unchanged = (sha256(manifest_path) == manifest_hash and sha256(baseline_path) == baseline_hash
                 and sha256(Path(manifest["source_file"])) == manifest["source_sha256"])
    result.update(run_status="complete", integrity_status="verified" if unchanged else "failed")
    write_json(out / "results.json", result)
    if not unchanged:
        raise ValueError("Inputs changed; follow-up invalid")
    summary = summarize_followup(result, baseline, manifest)
    write_json(out / "summary.json", summary)
    atomic_write_text(out / "report.md", report_followup(summary))
    if result["model_errors"] or any(r["status"] == "inference_error" for r in result["rows"]):
        raise RuntimeError("Follow-up had errors; inspect results, do not treat as successful validation")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download-cleanup", help="Download checksum-pinned official preprocessing only")
    download.add_argument("--source-cache", type=Path, default=ROOT / ".cache/publisher-cleanup")
    fast_download = sub.add_parser("download-fast", help="Explicit pinned public GPT-Neo download (~10.7 GB)")
    fast_download.add_argument("--cache-root", type=Path, default=ROOT / ".cache/models")
    for command in ("publisher", "fast"):
        p = sub.add_parser(command, help="Offline fixed-input comparison")
        p.add_argument("--manifest", type=Path, required=True)
        p.add_argument("--baseline", type=Path, required=True)
        p.add_argument("--out-dir", type=Path, required=True)
        p.add_argument("--cache-root", type=Path, default=ROOT / ".cache/models")
        if command == "publisher":
            p.add_argument("--source-cache", type=Path, default=ROOT / ".cache/publisher-cleanup")
        else:
            p.add_argument("--device", choices=["mps", "cpu"], default="cpu")
    args = parser.parse_args()
    try:
        if args.command == "download-fast":
            from huggingface_hub import snapshot_download
            snapshot_download(FAST_MODEL["repo"], revision=FAST_MODEL["revision"], token=False,
                              cache_dir=str(args.cache_root / "fast-detect-gpt-neo"), allow_patterns=FAST_FILES)
            print("Pinned public GPT-Neo cached; no interview content uploaded.")
            return
        if args.command == "download-cleanup":
            import httpx
            for name, spec in SOURCES.items():
                response = httpx.get(spec["url"], timeout=30)
                response.raise_for_status()
                if text_hash(response.text) != spec["sha256"]:
                    raise ValueError("Downloaded source checksum mismatch")
                atomic_write_text(args.source_cache / f"{name}.py", response.text)
            print("Reviewed checksum-pinned publisher preprocessing cached; no texts uploaded.")
            return
        if not args.out_dir.resolve().is_relative_to(ROOT / "data/processed"):
            raise ValueError("Private outputs must remain in ignored data/processed")
        if args.command == "publisher":
            specs = {name + "_publisher": {"checkpoint": MODELS[name], "preprocessing": spec,
                                           "score_type": "raw_ai_logit" if name == "mage" else "uncalibrated_sigmoid"}
                     for name, spec in SOURCES.items()}
            factory = lambda arm: PublisherCandidate(arm.removesuffix("_publisher"), args.cache_root, args.source_cache)
        else:
            specs = {"fast_gpt_neo": {**FAST_MODEL, "device": args.device}}
            factory = lambda arm: FastCandidate(args.cache_root / "fast-detect-gpt-neo", args.device)
        summary = run_followup(args.manifest, args.baseline, args.out_dir, specs, factory,
                               progress=lambda x: print(x, flush=True))
        print(f"Matched complete groups: {summary['matched_groups']}/{summary['original_complete_groups']}")
        print(f"Private report: {args.out_dir / 'report.md'}")
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"detector-followup: {exc}\n")


if __name__ == "__main__":
    main()
