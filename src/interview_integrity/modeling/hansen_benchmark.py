"""Offline Desklib evaluation on the HANSEN-TT held-out test CSV files.

The archive is read in place; no transcripts are extracted or written. Only
test.csv members are scored. Outputs contain aggregate scores and coverage.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from hashlib import sha256
from io import TextIOWrapper
import json
from pathlib import Path
import statistics
from zipfile import BadZipFile, ZipFile

from .beemo_benchmark import auroc
from .text_comparison import Candidate, COMMON_MAX_TOKENS, ROOT

EXPECTED_GENERATORS = {"ChatGPT", "PALM", "Vicuna13B"}
EXPECTED_DOMAINS = {"CEO", "SEC", "Spotify", "TED", "Tennis"}


def load_test_rows(archive: Path) -> list[dict]:
    """Load labeled HANSEN test text into memory without extracting files."""
    rows: list[dict] = []
    seen: set[str] = set()
    try:
        with ZipFile(archive) as zf:
            for member in zf.namelist():
                parts = member.split("/")
                if len(parts) != 3 or parts[0] != "HANSEN-TT" or parts[-1] != "test.csv":
                    continue
                folder = parts[1]
                if not folder.startswith("TT_"):
                    raise ValueError(f"Unexpected HANSEN test member: {member}")
                generator, domain = folder[3:].rsplit("_", 1)
                if generator not in EXPECTED_GENERATORS or domain not in EXPECTED_DOMAINS:
                    raise ValueError(f"Unexpected HANSEN group: {folder}")
                if folder in seen:
                    raise ValueError(f"Duplicate HANSEN test group: {folder}")
                seen.add(folder)
                with TextIOWrapper(zf.open(member), encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    if reader.fieldnames != ["label", "text"]:
                        raise ValueError(f"Unexpected CSV columns in {member}")
                    for index, item in enumerate(reader):
                        label, text = item.get("label"), item.get("text")
                        if label not in {"0", "1"} or not isinstance(text, str) or not text.strip():
                            raise ValueError(f"Invalid test row in {member} at row {index + 2}")
                        rows.append({"group": folder, "generator": generator, "domain": domain,
                                     "row_index": index, "label": int(label), "text": text})
    except BadZipFile as exc:
        raise ValueError("Input is not a valid ZIP archive") from exc
    expected = {f"TT_{model}_{domain}" for model in EXPECTED_GENERATORS for domain in EXPECTED_DOMAINS}
    if seen != expected:
        raise ValueError(f"Expected all 15 HANSEN test groups; found {len(seen)}")
    if not rows or {r["label"] for r in rows} != {0, 1}:
        raise ValueError("HANSEN test files must include both human and AI examples")
    return rows


def summarize(rows: list[dict], model_name: str, archive_sha256: str) -> dict:
    """Return aggregate threshold-free AUROC metrics and explicit coverage."""
    if not rows:
        raise ValueError("No HANSEN test rows")
    scored = [r for r in rows if r.get("status") == "scored"]

    def contrast(group: list[dict]) -> float | None:
        humans = [r["ai_text_score"] for r in group if r["label"] == 0 and r.get("status") == "scored"]
        ai = [r["ai_text_score"] for r in group if r["label"] == 1 and r.get("status") == "scored"]
        return auroc(humans, ai) if humans and ai else None

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["group"]].append(row)
    group_metrics = {}
    for group_name, group_rows in sorted(grouped.items()):
        metric = contrast(group_rows)
        group_metrics[group_name] = {
            "rows": len(group_rows), "scored": sum(r.get("status") == "scored" for r in group_rows),
            "human": sum(r["label"] == 0 for r in group_rows),
            "ai": sum(r["label"] == 1 for r in group_rows),
            "auroc": metric,
        }
    generators = {}
    for generator in sorted(EXPECTED_GENERATORS):
        subset = [r for r in rows if r["generator"] == generator]
        generators[generator] = {"rows": len(subset),
                                 "scored": sum(r.get("status") == "scored" for r in subset),
                                 "auroc": contrast(subset)}
    domains = {}
    for domain in sorted(EXPECTED_DOMAINS):
        subset = [r for r in rows if r["domain"] == domain]
        domains[domain] = {"rows": len(subset),
                           "scored": sum(r.get("status") == "scored" for r in subset),
                           "auroc": contrast(subset)}
    return {
        "dataset": "HANSEN-TT", "split": "test only", "label_mapping": {"0": "human", "1": "AI"},
        "model": model_name, "archive_sha256": archive_sha256,
        "total_rows": len(rows), "scored_rows": len(scored),
        "coverage": len(scored) / len(rows),
        "abstentions": dict(Counter(r.get("status", "unknown") for r in rows if r.get("status") != "scored")),
        "overall_auroc": contrast(rows),
        "mean_ai_text_score": {"human": statistics.mean(r["ai_text_score"] for r in scored if r["label"] == 0),
                               "AI": statistics.mean(r["ai_text_score"] for r in scored if r["label"] == 1)},
        "per_generator": generators, "per_domain": domains, "per_generator_domain": group_metrics,
        "threshold_selected": False, "classification_accuracy_reported": False,
        "training": False, "text_saved": False,
        "scope": "held-out written spoken-style text; not audio, ASR, technical interviews, or AI-use ground truth",
    }


def evaluate(archive: Path, cache_root: Path, *, factory=Candidate, progress=None) -> dict:
    rows = load_test_rows(archive)
    digest = sha256(archive.read_bytes()).hexdigest()
    candidate = factory("desklib", cache_root)
    try:
        for index, row in enumerate(rows, 1):
            try:
                tokens = candidate.token_count(row["text"])
                if tokens > COMMON_MAX_TOKENS:
                    row.update(status="over_token_limit", token_count=tokens)
                else:
                    row.update(candidate.score(row["text"]))
                    row.update(status="scored", token_count=tokens)
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                row.update(status="inference_error", error_type=type(exc).__name__)
            if progress and (index % 100 == 0 or index == len(rows)):
                progress(index, len(rows))
    finally:
        del candidate
    return summarize(rows, "desklib/ai-text-detector-v1.01@5fdea974", digest)


def report_text(summary: dict) -> str:
    lines = ["# HANSEN-TT Desklib held-out test", "",
             "Only the official `test.csv` files were evaluated. Label mapping is 0=human and 1=AI.",
             "AUROC measures ranking separation; no decision threshold or classification accuracy was selected.",
             "The model score is not a calibrated probability of interview AI assistance.",
             "Texts over the model's 512-token limit were excluded, not truncated. `n/a` means one class had no scored examples in that subgroup.", "",
             f"- Model: `{summary['model']}`",
             f"- Test rows: {summary['total_rows']:,}; scored: {summary['scored_rows']:,} ({summary['coverage']:.1%})",
             f"- Overall AUROC: **{summary['overall_auroc']:.4f}**",
             f"- Mean AI-text score: human {summary['mean_ai_text_score']['human']:.4f}; AI {summary['mean_ai_text_score']['AI']:.4f}",
             f"- Abstentions: {summary['abstentions']}", "",
             "## Results by generator", "", "| Generator | Rows | Scored | AUROC |", "| --- | ---: | ---: | ---: |"]
    for name, result in summary["per_generator"].items():
        auc = "n/a" if result["auroc"] is None else f"{result['auroc']:.4f}"
        lines.append(f"| {name} | {result['rows']} | {result['scored']} | {auc} |")
    lines += ["", "## Results by source domain", "", "| Domain | Rows | Scored | AUROC |", "| --- | ---: | ---: | ---: |"]
    for name, result in summary["per_domain"].items():
        auc = "n/a" if result["auroc"] is None else f"{result['auroc']:.4f}"
        lines.append(f"| {name} | {result['rows']} | {result['scored']} | {auc} |")
    lines += ["", "## Results by generator and domain", "",
              "| Group | Rows | Scored | AUROC |", "| --- | ---: | ---: | ---: |"]
    for name, result in summary["per_generator_domain"].items():
        auc = "n/a" if result["auroc"] is None else f"{result['auroc']:.4f}"
        lines.append(f"| {name} | {result['rows']} | {result['scored']} | {auc} |")
    lines += ["", "This is a held-out written-text benchmark. It does not validate the detector on spoken interview audio, ASR output, technical interviews, or real-time AI assistance.",
              "The archive checksum is recorded in the private aggregate JSON. No transcript text or row-level score is written by this evaluator.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=ROOT / ".cache/models")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.out_dir.resolve().is_relative_to(ROOT / "data/processed"):
        parser.error("Output must stay under ignored data/processed")
    if args.out_dir.exists():
        parser.error("Output directory already exists")
    args.out_dir.mkdir(parents=True)
    summary = evaluate(args.archive, args.cache_root,
                       progress=lambda done, total: print(f"desklib: {done}/{total} test rows", flush=True))
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.out_dir / "report.md").write_text(report_text(summary))
    print(f"HANSEN test AUROC: {summary['overall_auroc']:.4f}; coverage: {summary['scored_rows']}/{summary['total_rows']}")
    print(f"Private aggregate report: {args.out_dir / 'report.md'}")


if __name__ == "__main__":
    main()
