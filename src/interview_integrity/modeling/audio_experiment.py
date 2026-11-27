"""Local, paired VAD/prosody ablation. Not an AI-use detector or production scorer."""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import pickle
import shutil
import tempfile
import wave
import zipfile
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path

from .._fs import atomic_write_text
from ..audio.research_vad import SILERO_SETTINGS, SileroDetector, disagreement_seconds, read_window
from ..audio.vad import frame_levels, speech_intervals_from_levels, speech_threshold
from ..features.loudness import extract_loudness_features
from ..features.prosody import PROSODY_FEATURES, ProsodyExtractor
from ..features.timing import compute_timing_features
from ..media import run_ffmpeg
from .allsstar import _sha256, inventory
from .audio_baseline import AUDIO_FEATURES, _key, load_rows, prepare_data, train_baseline

SILERO_FEATURES = tuple("silero_" + name for name in AUDIO_FEATURES)
FEATURE_GROUPS = {"energy": AUDIO_FEATURES, "silero": SILERO_FEATURES,
                  "energy_prosody": AUDIO_FEATURES + PROSODY_FEATURES,
                  "silero_prosody": SILERO_FEATURES + PROSODY_FEATURES}


def select_audit(predictions):
    """20 targeted examples fixed from the OLD model, not selected to improve scores."""
    false_positive = sorted((r for r in predictions if r["actual"] == 0 and r["predicted"] == 1),
                            key=lambda r: -r["score"])[:10]
    false_negative = sorted((r for r in predictions if r["actual"] == 1 and r["predicted"] == 0),
                            key=lambda r: r["score"])[:5]
    correct = [r for r in predictions if r["actual"] == r["predicted"]]
    # Controls from both classes; deterministic, not a population sample.
    controls = ([r for r in correct if r["actual"] == 0][:3]
                + [r for r in correct if r["actual"] == 1][:2])
    return {_key(r): r for r in (*false_positive, *false_negative, *controls)}


def _audit_card(number, row, diagnostic, pcm, levels, prediction, out):
    name = f"clip-{number:03d}.wav"
    with wave.open(str(out / name), "wb") as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
        stream.writeframes(pcm)
    start, end = row["window_start"], row["window_end"]
    duration = end - start
    svg = ['<svg viewBox="0 0 900 140" role="img" aria-label="Energy levels and two VAD timelines">']
    points = " ".join(f"{100 + (levels.frame_time(i)[0] - start) / duration * 780:.2f},"
                      f"{55 - max(-90, min(0, db)) / 90 * -45:.2f}"
                      for i, db in enumerate(levels.db) if i % 2 == 0)
    svg.append(f'<polyline points="{points}" fill="none" stroke="black" stroke-width="1"/>')
    for y, detector in ((80, "energy"), (110, "silero")):
        svg.append(f'<text x="0" y="{y+12}">{detector}</text>')
        svg.append(f'<rect x="100" y="{y}" width="780" height="15" fill="#eee"/>')
        for lo, hi in diagnostic[detector + "_intervals"]:
            x, width = 100 + (lo - start) / duration * 780, (hi - lo) / duration * 780
            svg.append(f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="15" fill="black"/>')
    svg.append('</svg>')
    identity = html.escape(f'{row["recording_id"]} / {row["question_id"]}')
    actual = "READING" if prediction["actual"] else "SPONTANEOUS"
    predicted = "READING" if prediction["predicted"] else "SPONTANEOUS"
    return (f'<section><h2>{identity}</h2><p>Task label: {actual}; old model: {predicted}; '
            f'VAD disagreement: {diagnostic["disagreement_seconds"]:.2f} s.</p>'
            f'<audio controls preload="none" src="{name}"></audio>{"".join(svg)}</section>')


def extract_experiment(source, base_dir, out, *, detector=None, prosody=None):
    """Exactly the old cohort/windows, checksum checked; failures block comparison."""
    source, base_dir, out = Path(source), Path(base_dir), Path(out)
    if out.exists():
        raise ValueError("Output directory exists; choose a new experiment")
    rows = load_rows(base_dir / "features.jsonl")
    with (base_dir / "labels.csv").open(newline="") as stream:
        labels = list(csv.DictReader(stream))
    prepare_data(rows, labels)
    if {_key(r) for r in rows} != {_key(r) for r in labels}:
        raise ValueError("Comparison requires the identical fully labeled baseline cohort")
    recordings, counts = inventory(source)
    lookup = {Path(r.filename).stem: r for r in recordings}
    grouped = defaultdict(list)
    for row in rows:
        if row["recording_id"] not in lookup:
            raise ValueError("Baseline recording absent from source")
        record = lookup[row["recording_id"]]
        if record.task not in ("NWS", "ST1", "ST2") or record.participant_id != row["participant_id"]:
            raise ValueError("Unsupported task or inconsistent participant")
        lo, hi = row["window_start"], row["window_end"]
        if not all(math.isfinite(t) for t in (lo, hi)) or not 0 <= lo < hi <= 120:
            raise ValueError("Invalid fixed baseline window")
        if not row.get("audio_sha256"):
            raise ValueError("Source checksum required for paired experiment")
        grouped[row["recording_id"]].append(row)
    detector = detector if detector is not None else SileroDetector()
    prosody = prosody if prosody is not None else ProsodyExtractor()
    _, old_report = train_baseline(rows, labels, folds=5, seed=42, include_oof=True)
    audits = select_audit(old_report["oof_predictions"])
    out.mkdir(parents=True)
    audit_dir = out / "audit"; audit_dir.mkdir()
    enriched, diagnostics, failures, cards, audit_rows = [], [], [], [], []
    for index, (recording_id, windows) in enumerate(grouped.items(), 1):
        recording = lookup[recording_id]
        try:
            with tempfile.TemporaryDirectory(prefix="allsstar-prosody-") as directory:
                scratch = Path(directory)
                if recording.member is not None:
                    raw = scratch / "source.wav"
                    with zipfile.ZipFile(recording.source) as archive, archive.open(recording.member) as src, raw.open("xb") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
                else:
                    raw = Path(recording.source)
                checksum = _sha256(raw)
                if any(row["audio_sha256"] != checksum for row in windows):
                    raise ValueError("Source WAV differs from baseline checksum")
                normalized = scratch / "normalized.wav"
                run_ffmpeg(["-n", "-i", str(raw), "-t", str(max(r["window_end"] for r in windows)),
                            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(normalized)])
                for row in windows:
                    start, end = row["window_start"], row["window_end"]
                    samples, pcm = read_window(normalized, start, end)
                    levels = frame_levels(normalized, start=start, end=end)
                    energy = speech_intervals_from_levels(levels, speech_threshold(levels))
                    measured = compute_timing_features(speech_intervals=energy, answer_start=start, answer_end=end)
                    measured.update(extract_loudness_features(levels, energy))
                    if any(measured.get(name) != row["features"].get(name) for name in AUDIO_FEATURES):
                        raise ValueError("Recomputed energy features differ from original baseline")
                    silero = detector.detect(samples, start=start)
                    silero_values = compute_timing_features(speech_intervals=silero, answer_start=start, answer_end=end)
                    silero_values.update(extract_loudness_features(levels, silero))
                    values = prosody.extract(samples)
                    if set(values) != set(PROSODY_FEATURES):
                        raise ValueError("Incomplete prosody feature schema")
                    enriched.append({**row, "features": {**row["features"], **values,
                                      **{"silero_" + name: silero_values.get(name) for name in AUDIO_FEATURES}}})
                    diagnostic = {"recording_id": recording_id, "question_id": row["question_id"],
                                  "participant_id": row["participant_id"], "task": row["task"],
                                  "energy_intervals": energy, "silero_intervals": silero,
                                  "disagreement_seconds": disagreement_seconds(energy, silero),
                                  "silero_no_speech": not bool(silero)}
                    diagnostics.append(diagnostic)
                    if _key(row) in audits:
                        number = len(cards) + 1
                        cards.append(_audit_card(number, row, diagnostic, pcm, levels, audits[_key(row)], audit_dir))
                        audit_rows.append({"clip": f"clip-{number:03d}.wav", "recording_id": recording_id,
                                           "question_id": row["question_id"], "human_checked": "",
                                           "better_vad": "", "notes": ""})
        except Exception as exc:
            failures.append({"recording_id": recording_id, "error": f"{type(exc).__name__}: {exc}"})
        if index == 1 or index % 20 == 0 or index == len(grouped):
            print(f"Extracted {index}/{len(grouped)} recordings; {len(enriched)} windows; {len(failures)} failures", flush=True)
    # Restore ORIGINAL input order, making split assignments identical for every arm.
    order = {_key(row): index for index, row in enumerate(rows)}
    enriched.sort(key=lambda r: order[_key(r)])
    status = "ok" if not failures and len(enriched) == len(rows) else "partial"
    report = {"status": status, "source_inventory": counts, "baseline_windows": len(rows),
              "windows": len(enriched), "failures": failures, "silero_settings": SILERO_SETTINGS,
              "prosody_descriptors": list(PROSODY_FEATURES),
              "silero_no_speech_windows": sum(d["silero_no_speech"] for d in diagnostics),
              "mean_vad_disagreement_seconds": (sum(d["disagreement_seconds"] for d in diagnostics) / len(diagnostics)
                                                 if diagnostics else None),
              "audit_clips": len(cards), "human_audit_completed": False,
              "warning": "VAD disagreement is not VAD error; no timestamp ground truth or listening audit yet."}
    atomic_write_text(out / "features.jsonl", "".join(json.dumps(r, allow_nan=False) + "\n" for r in enriched))
    shutil.copyfile(base_dir / "labels.csv", out / "labels.csv")
    atomic_write_text(out / "diagnostics.jsonl", "".join(json.dumps(d, allow_nan=False) + "\n" for d in diagnostics))
    atomic_write_text(out / "quality.json", json.dumps(report, indent=2, allow_nan=False) + "\n")
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=["clip", "recording_id", "question_id", "human_checked", "better_vad", "notes"])
    writer.writeheader(); writer.writerows(audit_rows)
    atomic_write_text(audit_dir / "human-review.csv", text.getvalue())
    atomic_write_text(audit_dir / "index.html", '<!doctype html><html lang="en"><meta charset="utf-8">'
                      '<title>Private audio VAD audit</title><body><h1>Private audio VAD audit</h1>'
                      '<p>20 targeted old-model errors/controls, not a representative sample. Listen and annotate '
                      'human-review.csv. Black bars mark detected speech. Neither detector is ground truth.</p>'
                      + "".join(cards) + '</body></html>')
    return report


def compare_models(feature_dir, out, *, folds=5, seed=42):
    feature_dir, out = Path(feature_dir), Path(out)
    if out.exists():
        raise ValueError("Model output exists; choose a new experiment")
    if json.loads((feature_dir / "quality.json").read_text())["status"] != "ok":
        raise ValueError("Partial extraction cannot be compared")
    rows = load_rows(feature_dir / "features.jsonl")
    with (feature_dir / "labels.csv").open(newline="") as stream:
        labels = list(csv.DictReader(stream))
    out.mkdir(parents=True)
    results, reference_folds = {}, None
    for group, names in FEATURE_GROUPS.items():
        for classifier in ("logistic_regression", "svm_rbf"):
            name = group + "_" + classifier
            bundle, report = train_baseline(rows, labels, folds=folds, seed=seed, feature_names=names,
                                            classifier=classifier, include_oof=True)
            assignment = [(p["recording_id"], p["question_id"], p["fold"]) for p in report["oof_predictions"]]
            if reference_folds is not None and assignment != reference_folds:
                raise ValueError("Fold assignment changed across comparison arms")
            reference_folds = assignment
            directory = out / name; directory.mkdir()
            (directory / "model.pkl").write_bytes(pickle.dumps(bundle))
            atomic_write_text(directory / "metrics.json", json.dumps(report, indent=2, allow_nan=False) + "\n")
            results[name] = {k: report[k] for k in ("classifier", "rows", "participants", "oof_metrics", "missing_counts")}
            results[name]["feature_count"] = len(names)
            print(name, json.dumps(report["oof_metrics"]), flush=True)
    summary = {"status": "ok", "target": "READING_vs_SPONTANEOUS", "folds": folds, "seed": seed,
               "identical_fold_assignments": True, "results": results,
               "versions": {name: version(name) for name in ("opensmile", "silero-vad", "torch", "onnxruntime", "scikit-learn", "numpy")},
               "warning": "Exploratory comparison on previously evaluated folds, not a fresh test set. No AI-use claims."}
    atomic_write_text(out / "comparison.json", json.dumps(summary, indent=2, allow_nan=False) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--base-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.model_dir.exists():
            raise ValueError("Model output directory exists")
        report = extract_experiment(args.source, args.base_dir, args.out_dir)
        if report["status"] != "ok":
            parser.exit(2, "Extraction incomplete; comparison blocked. Inspect quality.json.\n")
        compare_models(args.out_dir, args.model_dir)
    except (ValueError, OSError, ImportError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"audio-delivery-experiment: {exc}\n")


if __name__ == "__main__":
    main()
