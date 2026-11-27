"""Manual audio inference mechanics; synthetic fixtures are not accuracy evidence."""
import json
import math
import subprocess
import sys

import pytest

from interview_integrity.modeling.audio_predict import (
    FEATURE_NAMES, complete_windows, evaluate_audio, predict_features, summarize, validate_bundle,
)
from interview_integrity.modeling.audio_baseline import LABELS
from interview_integrity.features.prosody import PROSODY_FEATURES
from .conftest import requires_ffmpeg, write_tone_wav


class Pipeline:
    classes_ = [0, 1]
    n_features_in_ = len(FEATURE_NAMES)

    def predict(self, rows):
        self.rows = rows
        return [1]

    def decision_function(self, rows):
        return [0.25]


def bundle():
    return {"pipeline": Pipeline(), "classifier": "svm_rbf", "feature_names": FEATURE_NAMES,
            "labels": LABELS.copy()}


def test_predict_import_does_not_load_optional_dependencies():
    subprocess.run([sys.executable, "-c", "import sys; import interview_integrity.modeling.audio_predict; "
                    "assert not {'torch','opensmile','silero_vad','sklearn','numpy'} & set(sys.modules)"], check=True)


@pytest.mark.parametrize("seconds,count", [(0, 0), (29.99, 0), (30, 1), (63.8, 2), (73.1, 2), (200, 4)])
def test_complete_windows_no_padding_and_training_cap(seconds, count):
    assert complete_windows(int(seconds * 16000)) == [(i * 30, (i + 1) * 30) for i in range(count)]


@pytest.mark.parametrize("changes", [{"classifier": "logistic_regression"}, {"feature_names": ("task",)},
                                    {"labels": {"READING": 0, "SPONTANEOUS": 1}}])
def test_incompatible_models_rejected(changes):
    with pytest.raises(ValueError, match="fixed"):
        validate_bundle({**bundle(), **changes})


def test_predict_only_named_features_and_uses_existing_imputer():
    model = bundle()
    features = dict.fromkeys(FEATURE_NAMES, 0.5)
    features[FEATURE_NAMES[0]] = None
    features.update(expected="READING", filename="reading", participant_id="private", audio_is_noisy=True)
    result = predict_features(model, features)
    assert result == {"prediction": "READING", "status": "predicted", "decision_margin": 0.25}
    assert len(model["pipeline"].rows[0]) == len(FEATURE_NAMES)
    assert math.isnan(model["pipeline"].rows[0][0])


@pytest.mark.parametrize("value", [True, float("inf"), float("nan")])
def test_invalid_feature_values_rejected(value):
    features = dict.fromkeys(FEATURE_NAMES, 0.5)
    features[FEATURE_NAMES[0]] = value
    with pytest.raises(ValueError, match="Invalid"):
        predict_features(bundle(), features)


def test_missing_schema_and_all_missing_rejected():
    with pytest.raises(ValueError, match="Missing feature"):
        predict_features(bundle(), {})
    with pytest.raises(ValueError, match="No usable"):
        predict_features(bundle(), dict.fromkeys(FEATURE_NAMES))


def test_silent_windows_abstain_without_model_execution():
    model = bundle()
    assert predict_features(model, {}, has_speech=False)["status"] == "insufficient_speech"
    assert not hasattr(model["pipeline"], "rows")


def test_summary_marks_disagreement_and_abstention():
    assert summarize([]) == "insufficient_duration"
    assert summarize([{"prediction": None}]) == "insufficient_speech"
    assert summarize([{"prediction": "READING"}, {"prediction": "SPONTANEOUS"}]) == "mixed"
    assert summarize([{"prediction": "READING"}] * 2) == "READING"


@requires_ffmpeg
def test_manual_file_processing_and_labels_do_not_change_prediction(tmp_path):
    pytest.importorskip("numpy")
    source = write_tone_wav(tmp_path / "source.wav", [(1, 10), (12, 28)], duration=31)

    class Detector:
        def detect(self, samples, *, start=0):
            return [(start + 1, start + 10), (start + 12, start + 28)]

    class Prosody:
        def extract(self, samples):
            return dict.fromkeys(PROSODY_FEATURES, 0.5)

    results = [evaluate_audio(source, bundle(), tmp_path / expected, expected=expected,
                              detector=Detector(), prosody=Prosody())
               for expected in LABELS]
    assert results[0]["windows"][0]["features"] == results[1]["windows"][0]["features"]
    assert results[0]["windows"][0]["prediction"] == results[1]["windows"][0]["prediction"]
    assert results[0]["windows"][0]["matches_user_label"] is False
    assert results[1]["windows"][0]["matches_user_label"] is True
    assert results[0]["used_seconds"] == 30 and results[0]["unused_decoded_tail_seconds"] == 1
    assert results[0]["label_source"] == "user_reported" and results[0]["asr_used"] is False
    assert json.loads((tmp_path / "READING" / "predictions.json").read_text())["score_type"] == "decision_margin"
    with pytest.raises(ValueError, match="already exists"):
        evaluate_audio(source, bundle(), tmp_path / "READING")


@requires_ffmpeg
def test_short_recording_has_no_fake_prediction(tmp_path):
    source = write_tone_wav(tmp_path / "short.wav", [], duration=1)
    result = evaluate_audio(source, bundle(), tmp_path / "result")
    assert result["windows"] == [] and result["recording_summary"] == "insufficient_duration"
