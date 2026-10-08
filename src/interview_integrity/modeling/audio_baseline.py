"""Reading versus spontaneous delivery baseline, requiring explicit ground truth.

No AI-assistance verdicts. Imports of optional ML dependencies are deferred until
training. The label CSV is separate from the existing pipeline's deception labels.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
from pathlib import Path

from .._fs import atomic_write_text
from ..features.prosody import PROSODY_FEATURES

AUDIO_FEATURES = (
    "speech_duration", "silence_duration", "pause_count", "long_pause_count",
    "mean_pause_duration", "max_pause_duration", "pause_duration_std",
    "total_pause_duration", "pause_ratio", "speech_segment_count",
    "mean_speech_segment_duration", "speech_segment_duration_std",
    "speech_level_std_db", "speech_level_range_db",
)
TRANSCRIPT_RATES = ("speech_rate_wpm", "articulation_rate_wpm", "speech_rate_cv")
LABELS = {"SPONTANEOUS": 0, "READING": 1}
LABEL_SOURCES = {"controlled_protocol", "dataset_annotation"}


def _key(row):
    key = tuple(str(row.get(k) or "").strip() for k in ("recording_id", "question_id"))
    if not all(key):
        raise ValueError("Every row needs recording_id and question_id")
    return key


def load_rows(path):
    path = Path(path)
    if path.is_dir():
        return [json.loads(p.read_text()) for p in sorted(path.glob("*.json"))]
    if path.suffix == ".csv":
        with path.open(newline="") as f:
            return list(csv.DictReader(f))
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    raise ValueError("Features must be a JSON directory, CSV, or JSONL")


def prepare_data(rows, labels, *, include_transcript_rates=False, feature_names=None):
    """Join explicit labels; never infer delivery from deception or assistance labels."""
    if not rows or not labels:
        raise ValueError("Nonempty feature data and explicit delivery labels are required")
    names = AUDIO_FEATURES + (TRANSCRIPT_RATES if include_transcript_rates else ())
    if feature_names is not None:
        names = tuple(feature_names)
        allowed = set(AUDIO_FEATURES + tuple("silero_" + n for n in AUDIO_FEATURES) + PROSODY_FEATURES)
        if include_transcript_rates:
            allowed.update(TRANSCRIPT_RATES)
        if not names or len(set(names)) != len(names) or not set(names) <= allowed:
            raise ValueError("Choose unique approved audio features, not quality/provenance/labels")
    index = {}
    for row in rows:
        key = _key(row)
        if key in index or row.get("augmentation"):
            raise ValueError("Duplicate answer or augmented input; use original unique answers")
        index[key] = row
    x, y, groups, keys = [], [], [], []
    seen, recording_groups, checksum_groups = set(), {}, {}
    for label in labels:
        key = _key(label)
        if key in seen or key not in index:
            raise ValueError(f"Duplicate label or missing features for {key}")
        seen.add(key)
        target = str(label.get("delivery_label") or "").strip().upper()
        if target not in LABELS:
            raise ValueError("delivery_label must be READING or SPONTANEOUS, not deception/AI labels")
        if label.get("label_source") not in LABEL_SOURCES:
            raise ValueError("label_source must be controlled_protocol or dataset_annotation")
        group = str(label.get("participant_id") or "").strip()
        if not group or group.lower().startswith(("unknown", "anon:", "placeholder")):
            raise ValueError("Real pseudonymous participant IDs are required; unknown IDs cannot prevent leakage")
        row = index[key]
        participant = str(row.get("participant_id") or "")
        if participant and not participant.lower().startswith("unknown") and participant != group:
            raise ValueError("Feature and label participant IDs disagree")
        for value, mapping in [(key[0], recording_groups), (row.get("video_sha256"), checksum_groups)]:
            if value and mapping.setdefault(value, group) != group:
                raise ValueError("One recording/checksum is assigned to multiple participants")
        if str(row.get("audio_is_silent") or "").lower() == "true":
            raise ValueError("Silent recording cannot be used for delivery training")
        features = row.get("features", row)
        values = []
        for name in names:
            raw = features.get(name)
            if raw is None or raw == "":
                values.append(float("nan"))
                continue
            if isinstance(raw, bool):
                raise ValueError(f"Feature {name} must be numeric, not boolean")
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError(f"Feature {name} must be finite or missing")
            values.append(value)
        if all(math.isnan(v) for v in values):
            raise ValueError(f"No usable audio features for {key}")
        x.append(values); y.append(LABELS[target]); groups.append(group); keys.append(key)
    if set(y) != {0, 1}:
        raise ValueError("Both READING and SPONTANEOUS labels are required")
    return x, y, groups, keys, names


def train_baseline(rows, labels, *, folds=3, seed=42, include_transcript_rates=False,
                   feature_names=None, classifier="logistic_regression", include_oof=False):
    import numpy as np
    import sklearn
    from sklearn.dummy import DummyClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score, roc_auc_score, precision_score, recall_score
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC

    if classifier not in ("logistic_regression", "svm_rbf"):
        raise ValueError("Unknown research classifier")
    data = prepare_data(rows, labels, include_transcript_rates=include_transcript_rates,
                        feature_names=feature_names)
    x, y, groups, keys, names = data
    x, y, groups = np.asarray(x), np.asarray(y), np.asarray(groups)
    if folds < 2 or any(len(set(groups[y == cls])) < folds for cls in (0, 1)):
        raise ValueError("Need at least folds distinct participants in each class, and folds >= 2")
    splits = list(StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed).split(x, y, groups))
    for train, test in splits:
        if set(y[train]) != {0, 1} or set(y[test]) != {0, 1}:
            raise ValueError("A grouped fold lacks a class; collect more balanced participant data")
        assert not set(groups[train]) & set(groups[test])

    def make_model():
        estimator = (LogisticRegression(class_weight="balanced", max_iter=2000, random_state=seed)
                     if classifier == "logistic_regression" else
                     SVC(C=1.0, kernel="rbf", gamma="scale", class_weight="balanced"))
        return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True),
                             StandardScaler(), estimator)

    predicted = np.empty(len(y), dtype=int)
    probability = np.empty(len(y), dtype=float)
    dummy_predicted = np.empty(len(y), dtype=int)
    fold_assignment = np.empty(len(y), dtype=int)
    fold_results = []
    for number, (train, test) in enumerate(splits):
        model = make_model().fit(x[train], y[train])
        predicted[test] = model.predict(x[test])
        probability[test] = (model.predict_proba(x[test])[:, 1] if classifier == "logistic_regression"
                             else model.decision_function(x[test]))
        fold_assignment[test] = number
        dummy_predicted[test] = DummyClassifier(strategy="most_frequent").fit(x[train], y[train]).predict(x[test])
        fold_results.append({"fold": number, "train_rows": len(train), "test_rows": len(test),
                             "train_participants": len(set(groups[train])), "test_participants": len(set(groups[test])),
                             "participant_overlap": 0,
                             "balanced_accuracy": float(balanced_accuracy_score(y[test], predicted[test]))})
    final_model = make_model().fit(x, y)
    report = {
        "target": "READING_vs_SPONTANEOUS", "positive_class": "READING",
        "warning": "Delivery mode is not AI use. Probabilities are uncalibrated research outputs, not cheating confidence.",
        "rows": len(y), "participants": len(set(groups)), "seed": seed, "folds": fold_results,
        "classifier": classifier,
        "score_type": "uncalibrated_probability" if classifier == "logistic_regression" else "decision_margin",
        "feature_names": list(names), "include_transcript_rates": include_transcript_rates,
        "missing_counts": {name: int(np.isnan(x[:, i]).sum()) for i, name in enumerate(names)},
        "class_counts": {label: int((y == value).sum()) for label, value in LABELS.items()},
        "oof_metrics": {"balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
                        "f1_reading": float(f1_score(y, predicted)), "roc_auc": float(roc_auc_score(y, probability)),
                        "confusion_matrix_spontaneous_reading": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
                        "precision_reading": float(precision_score(y, predicted, zero_division=0)),
                        "recall_reading": float(recall_score(y, predicted)),
                        "false_positive_rate_spontaneous": float((predicted[y == 0] == 1).mean()),
                        "dummy_balanced_accuracy": float(balanced_accuracy_score(y, dummy_predicted))},
        "versions": {"sklearn": sklearn.__version__, "numpy": np.__version__},
    }
    if include_oof:
        report["oof_predictions"] = [{"recording_id": key[0], "question_id": key[1],
                                      "participant_id": str(group), "fold": int(fold),
                                      "actual": int(actual), "predicted": int(pred), "score": float(score)}
                                     for key, group, fold, actual, pred, score in
                                     zip(keys, groups, fold_assignment, y, predicted, probability)]
    return {"pipeline": final_model, "feature_names": names, "labels": LABELS,
            "classifier": classifier}, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True)
    parser.add_argument("--labels", required=True, help="Ground-truth CSV; never infer labels from Michigan")
    parser.add_argument("--out-dir", default="data/models/reading_baseline")
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--include-transcript-rates", action="store_true")
    args = parser.parse_args()
    try:
        out = Path(args.out_dir)
        if out.exists():
            raise ValueError("Output directory already exists; choose a new run directory")
        with Path(args.labels).open(newline="") as f:
            labels = list(csv.DictReader(f))
        bundle, report = train_baseline(load_rows(args.features), labels, folds=args.folds, seed=args.seed,
                                        include_transcript_rates=args.include_transcript_rates)
        out.mkdir(parents=True)
        # Only load this trusted locally generated pickle; never unpickle third-party model files.
        (out / "model.pkl").write_bytes(pickle.dumps(bundle))
        atomic_write_text(out / "metrics.json", json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps(report["oof_metrics"], indent=2))
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f"audio-baseline: {exc}\n")


if __name__ == "__main__":
    main()
