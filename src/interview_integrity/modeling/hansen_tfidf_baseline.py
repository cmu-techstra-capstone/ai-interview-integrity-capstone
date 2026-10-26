"""Leakage-audited TF-IDF baseline on the gated HANSEN-TT archive.

Only aggregate metrics are returned. No source text or per-row predictions are
written. This is a text-authorship benchmark, not AI-assistance ground truth.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from io import TextIOWrapper
import json
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[3]


def _normalized_hash(text: str) -> str:
    normalized = " ".join(re.findall(r"\w+", text.casefold()))
    return sha256(normalized.encode("utf-8")).hexdigest()


def _read_splits(archive):
    rows = {"train": [], "test": []}
    try:
        with ZipFile(archive) as zf:
            for member in zf.namelist():
                split = member.rsplit("/", 1)[-1][:-4]
                if split not in rows or not member.startswith("HANSEN-TT/TT_"):
                    continue
                group = member.split("/")[-2]
                with TextIOWrapper(zf.open(member), encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    if reader.fieldnames != ["label", "text"]:
                        raise ValueError(f"Unexpected columns in {member}")
                    for row in reader:
                        if row["label"] not in {"0", "1"} or not row["text"].strip():
                            raise ValueError(f"Invalid row in {member}")
                        rows[split].append({
                            "label": int(row["label"]), "text": row["text"],
                            "group": group, "generator": group.split("_")[1],
                            "hash": _normalized_hash(row["text"]),
                        })
    except BadZipFile as exc:
        raise ValueError("Input is not a valid HANSEN-TT ZIP archive") from exc
    if not rows["train"] or not rows["test"]:
        raise ValueError("HANSEN archive must include train and test rows")
    return rows


def evaluate(archive) -> dict:
    """Train a small baseline after exact-text decontamination; test once."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import make_pipeline

    rows = _read_splits(archive)
    test_hashes = {row["hash"] for row in rows["test"]}
    train_by_hash = {}
    for row in rows["train"]:
        if row["hash"] not in test_hashes:
            train_by_hash.setdefault(row["hash"], row)
    test_by_hash = {}
    for row in rows["test"]:
        test_by_hash.setdefault(row["hash"], row)
    train = list(train_by_hash.values())
    test = list(test_by_hash.values())
    if {r["label"] for r in train} != {0, 1} or {r["label"] for r in test} != {0, 1}:
        raise ValueError("Decontaminated HANSEN splits must retain both labels")

    def clip(text: str) -> str:
        return " ".join(text.split()[:512])

    def fit_model():
        return make_pipeline(
            TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=50_000,
                            sublinear_tf=True),
            LogisticRegression(C=1, max_iter=200, solver="liblinear", random_state=0),
        )

    model = fit_model()
    model.fit([clip(r["text"]) for r in train], [r["label"] for r in train])
    scores = model.predict_proba([clip(r["text"]) for r in test])[:, 1]
    labels = [r["label"] for r in test]

    by_generator = {}
    for generator in sorted({r["generator"] for r in test}):
        indices = [i for i, row in enumerate(test) if row["generator"] == generator]
        group_labels = [labels[i] for i in indices]
        by_generator[generator] = {
            "unique_test_rows": len(indices),
            "auroc": float(roc_auc_score(group_labels, scores[indices]))
            if len(set(group_labels)) == 2 else None,
        }
    leave_one_generator_out = {}
    all_test_hashes = {row["hash"] for row in rows["test"]}
    for generator in sorted({r["generator"] for r in rows["test"]}):
        fit_by_hash = {}
        for row in rows["train"]:
            if row["generator"] != generator and row["hash"] not in all_test_hashes:
                fit_by_hash.setdefault(row["hash"], row)
        held_by_hash = {}
        for row in rows["test"]:
            if row["generator"] == generator:
                held_by_hash.setdefault(row["hash"], row)
        fit_rows, held_rows = list(fit_by_hash.values()), list(held_by_hash.values())
        fold = fit_model()
        fold.fit([clip(r["text"]) for r in fit_rows], [r["label"] for r in fit_rows])
        fold_scores = fold.predict_proba([clip(r["text"]) for r in held_rows])[:, 1]
        fold_labels = [r["label"] for r in held_rows]
        leave_one_generator_out[generator] = {
            "train_unique_rows": len(fit_rows), "test_unique_rows": len(held_rows),
            "auroc": float(roc_auc_score(fold_labels, fold_scores))
            if len(set(fold_labels)) == 2 else None,
        }
    return {
        "dataset": "HANSEN-TT", "evaluation": "official train/test; exact normalized text decontamination",
        "model": "word unigram/bigram TF-IDF + logistic regression",
        "train_rows_raw": len(rows["train"]), "test_rows_raw": len(rows["test"]),
        "train_unique_after_decontamination": len(train),
        "test_unique_by_normalized_text": len(test),
        "train_test_overlap_removed": len(rows["train"]) - len([r for r in rows["train"] if r["hash"] not in test_hashes]),
        "test_coverage": 1.0,
        "overall_auroc": float(roc_auc_score(labels, scores)),
        "by_generator": by_generator,
        "leave_one_generator_out": leave_one_generator_out,
        "raw_text_saved": False, "row_level_scores_saved": False,
        "scope": "spoken-style text authorship only; not interview AI-assistance detection",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True,
                        help="Path to the author-approved HANSEN-TT ZIP archive")
    parser.add_argument("--out", type=Path, required=True,
                        help="Aggregate JSON output path under ignored data/processed/")
    args = parser.parse_args()
    output = args.out.resolve()
    allowed_root = (ROOT / "data/processed").resolve()
    if not output.is_relative_to(allowed_root):
        parser.error("Output must stay under ignored data/processed/")
    if output.exists():
        parser.error("Output already exists; choose a new path to avoid overwriting results")
    output.parent.mkdir(parents=True, exist_ok=True)
    summary = evaluate(args.archive)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"HANSEN-TT AUROC: {summary['overall_auroc']:.4f}; coverage: {summary['test_coverage']:.1%}")
    print(f"Aggregate-only result: {output}")


if __name__ == "__main__":
    main()
