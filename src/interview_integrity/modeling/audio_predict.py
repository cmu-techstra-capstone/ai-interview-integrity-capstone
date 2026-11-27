"""Local manual test of the fixed Silero/prosody SVM; not an AI-use detector."""
from __future__ import annotations

import argparse
import json
import math
import pickle
import wave
from pathlib import Path

from .._fs import atomic_write_text
from ..audio.quality import assess_levels
from ..audio.research_vad import SILERO_SETTINGS, SileroDetector, read_window
from ..audio.vad import frame_levels
from ..features.loudness import extract_loudness_features
from ..features.prosody import PROSODY_FEATURES, ProsodyExtractor
from ..features.timing import compute_timing_features
from ..media import MediaError, ffprobe, first_stream, run_ffmpeg
from .allsstar import _sha256
from .audio_baseline import AUDIO_FEATURES, LABELS

FEATURE_NAMES = tuple("silero_" + name for name in AUDIO_FEATURES) + PROSODY_FEATURES
WINDOW_SECONDS = 30
MAX_WINDOWS = 4


def complete_windows(sample_count):
    """Same complete 30-second windows and first-120-second cap as training."""
    return [(i * WINDOW_SECONDS, (i + 1) * WINDOW_SECONDS)
            for i in range(min(sample_count // (16000 * WINDOW_SECONDS), MAX_WINDOWS))]


def validate_bundle(bundle):
    if (bundle.get("classifier") != "svm_rbf"
            or tuple(bundle.get("feature_names", ())) != FEATURE_NAMES
            or bundle.get("labels") != LABELS):
        raise ValueError("Expected the fixed Silero/prosody RBF SVM bundle")
    pipeline = bundle["pipeline"]
    if list(pipeline.classes_) != [0, 1] or pipeline.n_features_in_ != len(FEATURE_NAMES):
        raise ValueError("Model class order or input size differs from training")


def predict_features(bundle, features, *, has_speech=True):
    """No labels/filenames/quality flags enter the model. Missing values use its imputer."""
    validate_bundle(bundle)
    if not has_speech:
        return {"prediction": None, "status": "insufficient_speech", "decision_margin": None}
    vector = []
    for name in FEATURE_NAMES:
        if name not in features:
            raise ValueError(f"Missing feature key: {name}")
        raw = features[name]
        if raw is None:
            vector.append(float("nan"))
        elif isinstance(raw, bool) or not math.isfinite(float(raw)):
            raise ValueError(f"Invalid feature value: {name}")
        else:
            vector.append(float(raw))
    if all(math.isnan(value) for value in vector):
        raise ValueError("No usable audio features")
    pipeline = bundle["pipeline"]
    predicted = int(pipeline.predict([vector])[0])
    margin = float(pipeline.decision_function([vector])[0])
    if predicted not in (0, 1) or not math.isfinite(margin):
        raise ValueError("Invalid model output")
    return {"prediction": "READING" if predicted else "SPONTANEOUS",
            "status": "predicted", "decision_margin": margin}


def summarize(windows):
    """Conservative descriptive summary, not a validated recording-level classifier."""
    if not windows:
        return "insufficient_duration"
    predictions = [row["prediction"] for row in windows if row["prediction"] is not None]
    if len(predictions) != len(windows):
        return "insufficient_speech"
    return predictions[0] if len(set(predictions)) == 1 else "mixed"


def evaluate_audio(source, bundle, out, *, expected=None, detector=None, prosody=None,
                   model_sha256=None):
    source, out = Path(source), Path(out)
    validate_bundle(bundle)
    if expected is not None and expected not in LABELS:
        raise ValueError("Expected label must be READING or SPONTANEOUS")
    if out.exists():
        raise ValueError("Output already exists; choose a new private directory")
    probe = ffprobe(source)
    if first_stream(probe, "audio") is None:
        raise ValueError("Input has no audio stream")
    source_duration = float(probe["format"]["duration"])
    if not math.isfinite(source_duration) or source_duration <= 0:
        raise ValueError("Invalid media duration")
    out.mkdir(parents=True)
    normalized = out / "normalized.wav"
    run_ffmpeg(["-n", "-i", str(source), "-t", "120", "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(normalized)])
    with wave.open(str(normalized), "rb") as stream:
        spans = complete_windows(stream.getnframes())
        decoded_duration = stream.getnframes() / stream.getframerate()
    detector = detector if detector is not None else (SileroDetector() if spans else None)
    prosody = prosody if prosody is not None else (ProsodyExtractor() if spans else None)
    windows = []
    for start, end in spans:
        samples, _ = read_window(normalized, start, end)
        levels = frame_levels(normalized, start=start, end=end)
        quality = assess_levels(levels)
        intervals = detector.detect(samples, start=start)
        timing = compute_timing_features(speech_intervals=intervals, answer_start=start, answer_end=end)
        timing.update(extract_loudness_features(levels, intervals))
        features = {"silero_" + name: timing.get(name) for name in AUDIO_FEATURES}
        if intervals and not quality.is_silent:
            values = prosody.extract(samples)
            if set(values) != set(PROSODY_FEATURES):
                raise ValueError("Incomplete prosody feature schema")
            features.update(values)
        else:
            features.update(dict.fromkeys(PROSODY_FEATURES))
        prediction = predict_features(bundle, features,
                                      has_speech=bool(intervals) and not quality.is_silent)
        windows.append({"start": start, "end": end, **prediction,
                        "quality_flags": quality.flags, "quality": quality.to_features(),
                        "speech_intervals": intervals, "features": features,
                        "matches_user_label": (prediction["prediction"] == expected
                                               if expected and prediction["prediction"] else None)})
    result = {"source_sha256": _sha256(source), "model_sha256": model_sha256,
              "source_duration_seconds": source_duration, "decoded_duration_seconds": decoded_duration,
              "used_seconds": len(spans) * WINDOW_SECONDS,
              "unused_decoded_tail_seconds": decoded_duration - len(spans) * WINDOW_SECONDS,
              "beyond_120_second_cap_seconds": max(0, source_duration - 120),
              "expected_delivery": expected, "label_source": "user_reported" if expected else None,
              "target": "READING_vs_SPONTANEOUS", "score_type": "decision_margin",
              "silero_settings": SILERO_SETTINGS, "feature_names": list(FEATURE_NAMES),
              "recording_summary": summarize(windows), "windows": windows,
              "asr_used": False, "retrained": False,
              "warning": "Margins are not probabilities. Reading is not AI use. Personal smoke test, "
                         "not population accuracy; English training data; language transfer unvalidated."}
    atomic_write_text(out / "predictions.json", json.dumps(result, indent=2, allow_nan=False) + "\n")
    lines = ["# Audio delivery manual test", "", result["warning"], "",
             f"User-reported delivery: {expected or 'not provided'}. Summary: {result['recording_summary']}.",
             f"Duration: {source_duration:.3f} seconds; analyzed: {result['used_seconds']} seconds.",
             "", "| Window seconds | Prediction | SVM margin | Quality flags |",
             "| --- | --- | --- | --- |"]
    for row in windows:
        margin = f"{row['decision_margin']:.4f}" if row['decision_margin'] is not None else "n/a"
        lines.append(f"| {row['start']} to {row['end']} | {row['prediction'] or row['status']} | "
                     f"{margin} | {', '.join(row['quality_flags']) or 'none'} |")
    lines.extend(["", "Positive margin favors READING; negative favors SPONTANEOUS. "
                  "The summary describes window agreement only; it is not a calibrated confidence score.",
                  "Expected delivery is evaluation metadata, never a predictor. No ASR or training was run.",
                  "Recordings and this report contain private data; do not commit them to Git.", ""])
    atomic_write_text(out / "report.md", "\n".join(lines))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--trusted-model", type=Path, required=True,
                        help="Local model trained by this project ONLY; pickle can execute arbitrary code")
    parser.add_argument("--out-dir", type=Path, required=True, help="New private, Git-ignored directory")
    parser.add_argument("--expected", choices=tuple(LABELS), help="User-reported label for comparison only")
    args = parser.parse_args()
    try:
        # Explicit trust boundary: never use a downloaded/untrusted pickle here.
        bundle = pickle.loads(args.trusted_model.read_bytes())
        result = evaluate_audio(args.audio, bundle, args.out_dir, expected=args.expected,
                                model_sha256=_sha256(args.trusted_model))
        print(json.dumps({key: result[key] for key in ("recording_summary", "used_seconds", "score_type")}))
        print(f"Private report: {args.out_dir / 'report.md'}")
    except (ValueError, OSError, ImportError, MediaError, pickle.UnpicklingError) as exc:
        parser.exit(2, f"audio-predict: {exc}\n")


if __name__ == "__main__":
    main()
