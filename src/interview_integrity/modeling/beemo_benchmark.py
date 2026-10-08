"""Pinned Beemo paired-text stress test; not an audio/interview validation.

Freeze category-stratified prompt groups BEFORE inference. No retraining, text
rewriting, threshold fitting, source-label leakage or model selection. Optional
dependencies are lazy. Individual outputs/source content stay Git-ignored.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gc
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import statistics
import time

from .._fs import atomic_write_text
from .text_comparison import Candidate, COMMON_MAX_TOKENS, MODELS, runtime_versions, validated_scores
from .transcript_baseline import MIN_WORDS, ROOT, sha256, word_count

DATASET = "toloka/beemo"
REVISION = "9c014107fe9b85c4c784c1ce3a43b0b7b0a6d162"
PARQUET = "data/train-00000-of-00001.parquet"
SEED = 20261008
FIELDS = {"human": "human_output", "ai_original": "model_output", "ai_expert_edited": "human_edits"}
LABELS = {"human": 0, "ai_original": 1, "ai_expert_edited": 1}
WARNINGS = [
    "External written-text stress test, not spoken technical interviews or end-to-end ASR validation.",
    "Expert-edited machine text is a hybrid AI-assisted positive under our project definition.",
    "Training overlap is not fully auditable: do not claim guaranteed independent unseen data.",
    "No threshold selection, classification accuracy, calibrated cheating probability or model winner.",
    "AUROC is conditional on the common complete groups; report all exclusions and coverage.",
    "Identical raw checkpoint inputs; publisher-specific preprocessing is not reproduced.",
    "Beemo components have separate upstream licences; no raw content/weights redistribution.",
]


def write_json(path: Path, value: dict) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rank(seed: int, *parts) -> str:
    return text_hash(json.dumps([seed, *parts], ensure_ascii=False))


def select_groups(rows: list[dict], count: int = 200, seed: int = SEED) -> list[dict]:
    """One row per prompt, stratified by category, independent of text length/scores."""
    if not rows or isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("Positive group count and nonempty dataset required")
    by_prompt = defaultdict(list)
    seen_ids = set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("prompt_id"), str)
                or not row["prompt_id"] or not isinstance(row.get("category"), str)
                or not row["category"] or not isinstance(row.get("model"), str)
                or not row["model"] or not isinstance(row.get("id"), int)
                or isinstance(row["id"], bool) or row["id"] < 0):
            raise ValueError("Invalid Beemo row metadata")
        if row["id"] in seen_ids:
            raise ValueError("Duplicate source row ID")
        seen_ids.add(row["id"])
        if any(not isinstance(row.get(field), str) or not row[field].strip() for field in FIELDS.values()):
            raise ValueError("Missing text field; do not silently replace rows")
        by_prompt[row["prompt_id"]].append(row)
    strata = defaultdict(list)
    for prompt_id, group in by_prompt.items():
        if len({(r["category"], r["human_output"]) for r in group}) != 1:
            raise ValueError("Inconsistent prompt group")
        representative = min(group, key=lambda r: _rank(seed, prompt_id, r["id"]))
        strata[representative["category"]].append(representative)
    categories = sorted(strata)
    base, remainder = divmod(count, len(categories))
    selected = []
    for index, category in enumerate(categories):
        quota = base + int(index < remainder)
        if len(strata[category]) < quota:
            raise ValueError("Insufficient category groups; no post-hoc quota replacement")
        selected.extend(sorted(strata[category], key=lambda r: _rank(seed, r["prompt_id"]))[:quota])
    return selected


def prepare(rows: list[dict], source: Path, out: Path, *, count=200, seed=SEED) -> dict:
    if out.exists():
        raise ValueError("Output already exists")
    before = sha256(source)
    selected = select_groups(rows, count=count, seed=seed)
    samples = []
    for row in selected:
        for variant, field in FIELDS.items():
            text = row[field].strip()  # Same boundary whitespace treatment as Transcript.text.
            samples.append({"id": f"beemo-{row['id']}-{variant}", "source_row_id": row["id"],
                            "prompt_id": row["prompt_id"], "category": row["category"],
                            "generator": row["model"], "variant": variant, "label": LABELS[variant],
                            "source_field": field, "text": text, "text_sha256": text_hash(text),
                            "word_count": word_count(text), "language": "en"})
    manifest = {"purpose": "beemo_paired_text_stress_test", "dataset": DATASET, "revision": REVISION,
                "source_file": str(source.resolve()), "source_sha256": before,
                "dataset_rows": len(rows), "dataset_prompt_groups": len({r["prompt_id"] for r in rows}),
                "selected_groups": len(selected), "seed": seed, "samples": samples,
                "sampling": "equal category quotas, SHA256 seeded prompt order, one row per prompt",
                "selection_independent_of_scores_and_length": True, "preprocessing": "boundary_whitespace_only",
                "variant_labels": LABELS, "models_planned": list(MODELS), "threshold_selected": False,
                "min_words": MIN_WORDS, "common_max_tokens": COMMON_MAX_TOKENS,
                "bootstrap_draws": 1000, "bootstrap_unit": "paired_prompt_group",
                "warnings": WARNINGS,
                "category_counts": dict(Counter(r["category"] for r in selected)),
                "generator_counts": dict(Counter(r["model"] for r in selected))}
    if sha256(source) != before:
        raise ValueError("Source changed during preparation")
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "manifest.json", manifest)
    return manifest


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text())
    if (not isinstance(manifest, dict) or manifest.get("purpose") != "beemo_paired_text_stress_test"
            or manifest.get("dataset") != DATASET or manifest.get("revision") != REVISION
            or manifest.get("variant_labels") != LABELS or manifest.get("min_words") != MIN_WORDS
            or manifest.get("common_max_tokens") != COMMON_MAX_TOKENS
            or manifest.get("bootstrap_draws") != 1000 or manifest.get("threshold_selected") is not False
            or not isinstance(manifest.get("samples"), list) or not manifest["samples"]):
        raise ValueError("Invalid benchmark protocol")
    seen, groups = set(), defaultdict(set)
    for sample in manifest["samples"]:
        if (not isinstance(sample, dict) or not isinstance(sample.get("id"), str)
                or not isinstance(sample.get("text"), str) or not isinstance(sample.get("prompt_id"), str)
                or sample.get("variant") not in FIELDS or sample.get("language") != "en"
                or sample.get("label") != LABELS[sample["variant"]]
                or sample.get("source_field") != FIELDS[sample["variant"]]
                or sample.get("text_sha256") != text_hash(sample["text"])
                or sample.get("word_count") != word_count(sample["text"])):
            raise ValueError("Invalid sample/hash/label")
        if sample["id"] in seen or sample["variant"] in groups[sample["prompt_id"]]:
            raise ValueError("Duplicate sample or prompt variant")
        seen.add(sample["id"])
        groups[sample["prompt_id"]].add(sample["variant"])
    if any(v != set(FIELDS) for v in groups.values()) or len(groups) != manifest.get("selected_groups"):
        raise ValueError("Incomplete paired groups")
    if sha256(Path(manifest["source_file"])) != manifest["source_sha256"]:
        raise ValueError("Dataset checksum changed")
    return manifest


def auroc(negatives: list[float], positives: list[float]) -> float:
    """Tie-aware Mann-Whitney AUROC; high score means positive. No threshold."""
    if (not negatives or not positives or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                             or not math.isfinite(v) for v in negatives + positives)):
        raise ValueError("Both finite score classes required")
    ordered = sorted([(v, 0) for v in negatives] + [(v, 1) for v in positives])
    seen_neg, concordance = 0, 0.0
    for _, tied in itertools.groupby(ordered, key=lambda item: item[0]):
        group = list(tied)
        n = sum(label == 0 for _, label in group)
        p = len(group) - n
        concordance += p * (seen_neg + n / 2)
        seen_neg += n
    return concordance / (len(negatives) * len(positives))


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def bootstrap_auc(negatives: list[float], positives: list[float], seed: int, draws=1000):
    if len(negatives) != len(positives) or not negatives:
        raise ValueError("Paired bootstrap needs equal nonempty groups")
    if len(negatives) < 2:
        return None
    rng, values = random.Random(seed), []
    for _ in range(draws):
        indexes = [rng.randrange(len(negatives)) for _ in negatives]
        values.append(auroc([negatives[i] for i in indexes], [positives[i] for i in indexes]))
    return [quantile(values, .025), quantile(values, .975)]


def summarize(result: dict, manifest: dict) -> dict:
    if result.get("integrity_status") != "verified" or result.get("run_status") != "complete":
        raise ValueError("Cannot summarize unverified/incomplete run")
    samples = manifest["samples"]
    names = list(result["models"])
    lookup = {}
    for row in result["rows"]:
        key = (row["model"], row["prompt_id"], row["variant"])
        if key in lookup:
            raise ValueError("Duplicate result row")
        lookup[key] = row
    prompts = sorted({s["prompt_id"] for s in samples})
    if any((name, prompt, variant) not in lookup for name in names for prompt in prompts for variant in FIELDS):
        raise ValueError("Missing result rows")
    complete = [p for p in prompts if all(lookup[name, p, v]["status"] == "scored_exploratory"
                                        for name in names for v in FIELDS)]
    summary = {"selected_groups": len(prompts), "common_complete_groups": len(complete),
               "common_complete_group_fraction": len(complete) / len(prompts),
               "common_prompt_ids": complete, "threshold_selected": False, "accuracy_estimated": False,
               "model_selected": None, "scope": "conditional written-text stress test", "models": {}}
    for name in names:
        coverage = {}
        for variant in FIELDS:
            rows = [lookup[name, p, variant] for p in prompts]
            scored = [r["ai_text_score"] for r in rows if r["status"] == "scored_exploratory"]
            for r in rows:
                if r["status"] == "scored_exploratory":
                    validated_scores(r)
            coverage[variant] = {"total": len(rows), "scored": len(scored),
                                 "unscored_fraction": 1 - len(scored) / len(rows),
                                 "statuses": dict(Counter(r["status"] for r in rows)),
                                 "all_scored_mean": statistics.mean(scored) if scored else None,
                                 "all_scored_median": statistics.median(scored) if scored else None}
        metrics = {"coverage": coverage, "common_groups": len(complete), "contrasts": {}, "paired_score_means": {}}
        if complete:
            scores = {v: [lookup[name, p, v]["ai_text_score"] for p in complete] for v in FIELDS}
            metrics["paired_score_means"] = {v: statistics.mean(x) for v, x in scores.items()}
            for variant in ("ai_original", "ai_expert_edited"):
                human, positive = scores["human"], scores[variant]
                metrics["contrasts"][variant] = {"auroc": auroc(human, positive),
                    "bootstrap_95_percentile_interval": bootstrap_auc(human, positive, manifest["seed"], manifest["bootstrap_draws"]),
                    "bootstrap_unit": "paired_prompt_group", "bootstrap_draws": manifest["bootstrap_draws"],
                    "within_prompt_positive_higher_fraction": statistics.mean(float(p > h) for h, p in zip(human, positive)),
                    "within_prompt_tie_fraction": statistics.mean(float(p == h) for h, p in zip(human, positive))}
            metrics["edited_minus_original_mean_score"] = statistics.mean(
                e - o for e, o in zip(scores["ai_expert_edited"], scores["ai_original"]))
            metrics["expert_edit_lowered_score_fraction"] = statistics.mean(
                float(e < o) for e, o in zip(scores["ai_expert_edited"], scores["ai_original"]))
        summary["models"][name] = metrics
    return summary


def report_text(summary: dict, manifest: dict) -> str:
    lines = ["# Beemo paired-text stress test", "", *["- " + w for w in WARNINGS], "",
             f"Dataset: `{DATASET}` @ `{REVISION}`; seed {manifest['seed']}.",
             f"Frozen selection: {summary['selected_groups']} prompt groups, three variants each.",
             f"Common complete groups across all models/variants: **{summary['common_complete_groups']}**.",
             "AUROC: 0.5 means no ranking separation, 1.0 perfect ranking; NOT classification accuracy.",
             "Bootstrap intervals resample paired prompt groups (1000 draws). Generalization/overlap uncertainty is not captured.", "",
             "| Model | Original AI vs human AUROC [95% CI] | Expert-edited AI vs human AUROC [95% CI] | Human mean score | AI mean score | Edited mean score |",
             "| --- | --- | --- | --- | --- | --- |"]
    for name, metrics in summary["models"].items():
        contrasts = []
        for variant in ("ai_original", "ai_expert_edited"):
            item = metrics["contrasts"].get(variant)
            if item is None:
                contrasts.append("n/a")
            else:
                ci = item["bootstrap_95_percentile_interval"]
                contrasts.append(f"{item['auroc']:.4f}" + (f" [{ci[0]:.4f}, {ci[1]:.4f}]" if ci else ""))
        means = [metrics["paired_score_means"].get(v) for v in FIELDS]
        lines.append("| " + " | ".join([name, *contrasts, *["n/a" if x is None else f"{x:.4f}" for x in means]]) + " |")
    lines += ["", "## Coverage on the full frozen selection", "",
              "| Model | Variant | Scored / selected | Unscored | Reasons |", "| --- | --- | --- | --- | --- |"]
    for name, metrics in summary["models"].items():
        for variant, coverage in metrics["coverage"].items():
            reasons = ", ".join(f"{k}: {v}" for k, v in coverage["statuses"].items() if k != "scored_exploratory") or "none"
            lines.append(f"| {name} | {variant} | {coverage['scored']} / {coverage['total']} | {coverage['unscored_fraction']:.1%} | {reasons} |")
    lines += ["", "No excluded examples were replaced. No threshold/model winner selected; no interview/hiring accuracy claim.",
              "The same complete prompt groups are used for every model and both contrasts.",
              "No ASR, fine-tuning, LLM cleanup, multimodal fusion or interview-content upload.", ""]
    return "\n".join(lines)


def run(manifest_path: Path, out: Path, cache_root: Path, *, factory=Candidate, progress=None) -> dict:
    if out.exists():
        raise ValueError("Output already exists")
    before = sha256(manifest_path)
    manifest = load_manifest(manifest_path)
    if sha256(manifest_path) != before:
        raise ValueError("Manifest changed during loading")
    out.mkdir(parents=True, exist_ok=False)
    result = {"purpose": manifest["purpose"], "dataset": DATASET, "revision": REVISION,
              "manifest_file": str(manifest_path.resolve()), "manifest_sha256": before,
              "source_sha256": manifest["source_sha256"], "models": MODELS,
              "runtime_versions": runtime_versions(), "rows": [], "model_errors": {},
              "integrity_status": "pending", "run_status": "running", "asr_used": False,
              "training": False, "threshold_selected": False, "model_selected": None,
              "sends_content_externally": False, "warnings": WARNINGS}
    for name in MODELS:
        candidate, loaded = None, time.monotonic()
        try:
            candidate = factory(name, cache_root)
        except (ImportError, OSError, ValueError, RuntimeError) as exc:
            result["model_errors"][name] = str(exc)
        load_seconds = time.monotonic() - loaded
        for index, sample in enumerate(manifest["samples"], 1):
            row = {k: sample[k] for k in ("id", "source_row_id", "prompt_id", "category", "generator",
                                          "variant", "label", "text_sha256", "word_count")}
            row.update(model=name, ai_text_score=None, human_score=None, token_count=None,
                       score_type=MODELS[name]["score_type"], model_load_seconds=load_seconds,
                       text_truncated=False, status="not_evaluated")
            started = time.monotonic()
            if name in result["model_errors"]:
                row["status"] = "model_error"
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
                except (ImportError, OSError, ValueError, RuntimeError) as exc:
                    row.update(status="inference_error", error=str(exc))
            row["inference_seconds"] = time.monotonic() - started
            result["rows"].append(row)
            if index % 50 == 0 or index == len(manifest["samples"]):
                write_json(out / "results.json", result)
                if progress is not None:
                    progress(f"{name}: {index}/{len(manifest['samples'])} samples processed (including abstentions)")
        del candidate
        gc.collect()
    try:
        unchanged = (sha256(manifest_path) == before
                     and sha256(Path(manifest["source_file"])) == manifest["source_sha256"])
    except OSError:
        unchanged = False
    result["integrity_status"] = "verified" if unchanged else "failed"
    result["run_status"] = "complete"
    write_json(out / "results.json", result)
    if not unchanged:
        raise ValueError("Inputs changed during inference; results invalid")
    summary = summarize(result, manifest)
    write_json(out / "summary.json", summary)
    atomic_write_text(out / "report.md", report_text(summary, manifest))
    return summary


def dataset_path(cache: Path) -> Path:
    from huggingface_hub import hf_hub_download
    return Path(hf_hub_download(DATASET, PARQUET, repo_type="dataset", revision=REVISION,
                               cache_dir=str(cache), local_files_only=True, token=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download", help="Explicit public data download only")
    prepare_parser = sub.add_parser("prepare", help="Freeze input selection before scoring")
    inference = sub.add_parser("run", help="Offline inference and threshold-free metrics")
    for command in (download, prepare_parser):
        command.add_argument("--dataset-cache", type=Path, default=ROOT / ".cache/datasets/beemo")
    prepare_parser.add_argument("--groups", type=int, default=200)
    prepare_parser.add_argument("--seed", type=int, default=SEED)
    prepare_parser.add_argument("--out-dir", type=Path, required=True)
    inference.add_argument("--manifest", type=Path, required=True)
    inference.add_argument("--out-dir", type=Path, required=True)
    inference.add_argument("--cache-root", type=Path, default=ROOT / ".cache/models")
    args = parser.parse_args()
    try:
        if args.command == "download":
            from huggingface_hub import hf_hub_download
            for filename in (PARQUET, "README.md"):
                hf_hub_download(DATASET, filename, repo_type="dataset", revision=REVISION,
                                cache_dir=str(args.dataset_cache), token=False)
            print("Pinned public Beemo data cached; no interview content uploaded.")
            return
        if not args.out_dir.resolve().is_relative_to(ROOT / "data/processed"):
            raise ValueError("Private output must stay under ignored data/processed")
        if args.command == "prepare":
            import pyarrow.parquet as pq
            source = dataset_path(args.dataset_cache)
            manifest = prepare(pq.read_table(source).to_pylist(), source, args.out_dir,
                               count=args.groups, seed=args.seed)
            print(json.dumps({k: manifest[k] for k in ("selected_groups", "category_counts", "generator_counts")}, indent=2))
            print(f"Frozen manifest: {args.out_dir / 'manifest.json'}")
        else:
            summary = run(args.manifest, args.out_dir, args.cache_root, progress=lambda x: print(x, flush=True))
            print(f"Common complete groups: {summary['common_complete_groups']}/{summary['selected_groups']}")
            print(f"Private report: {args.out_dir / 'report.md'}")
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"beemo-benchmark: {exc}\n")


if __name__ == "__main__":
    main()
