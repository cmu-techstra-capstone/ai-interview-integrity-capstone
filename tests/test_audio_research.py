"""Research regression fixtures test mechanics, not real detector performance."""
import json
import subprocess
import sys

import pytest

from interview_integrity.audio.research_vad import disagreement_seconds, read_window, sample_intervals
from interview_integrity.features.prosody import PROSODY_FEATURES, PROSODY_DESCRIPTORS
from interview_integrity.modeling.audio_baseline import prepare_data, train_baseline
from interview_integrity.modeling.audio_experiment import extract_experiment, select_audit, compare_models
from interview_integrity.modeling.allsstar import import_audio
from .conftest import requires_ffmpeg, write_tone_wav
from .test_audio_baseline import fixtures


def test_optional_research_imports_do_not_load_heavy_dependencies():
    subprocess.run([sys.executable, "-c", "import sys; import interview_integrity.modeling.audio_experiment; "
                    "assert not {'torch','opensmile','silero_vad','sklearn','numpy'} & set(sys.modules)"], check=True)


@pytest.mark.parametrize("feature", ["task", "participant_id", "audio_snr_db", "audio_is_noisy", "delivery_label"])
def test_quality_provenance_and_labels_cannot_be_predictors(feature):
    rows, labels = fixtures()
    with pytest.raises(ValueError, match="approved audio"):
        prepare_data(rows, labels, feature_names=(feature,))


def test_duplicate_feature_names_rejected():
    rows, labels = fixtures()
    with pytest.raises(ValueError, match="unique"):
        prepare_data(rows, labels, feature_names=("pause_ratio", "pause_ratio"))


def test_no_absolute_pitch_or_loudness_in_selected_prosody():
    assert len(PROSODY_FEATURES) == 20 and len(set(PROSODY_FEATURES)) == 20
    assert "F0semitoneFrom27.5Hz_sma3nz_amean" not in PROSODY_DESCRIPTORS
    assert "loudness_sma3_amean" not in PROSODY_DESCRIPTORS
    assert "equivalentSoundLevel_dBp" not in PROSODY_DESCRIPTORS


def test_svm_and_oof_keep_identical_speaker_folds():
    pytest.importorskip("sklearn")
    rows, labels = fixtures()
    for row in rows:
        row["silero_pause_ratio"] = row["pause_ratio"]
        row[PROSODY_FEATURES[0]] = row["pause_ratio"] * 2
    _, original = train_baseline(rows, labels, folds=3, include_oof=True)
    _, extended = train_baseline(rows, labels, folds=3, include_oof=True, classifier="svm_rbf",
                                 feature_names=("silero_pause_ratio", PROSODY_FEATURES[0]))
    assert [(r["participant_id"], r["fold"]) for r in original["oof_predictions"]] == [
        (r["participant_id"], r["fold"]) for r in extended["oof_predictions"]]
    assert extended["score_type"] == "decision_margin"
    assert all(f["participant_overlap"] == 0 for f in extended["folds"])


def test_unknown_classifier_rejected():
    pytest.importorskip("sklearn")
    rows, labels = fixtures()
    with pytest.raises(ValueError, match="Unknown"):
        train_baseline(rows, labels, classifier="unapproved")


def test_interval_offsets_and_disagreement():
    assert sample_intervals([{"start": 1600, "end": 3200}], samples=16000, start=30) == [(30.1, 30.2)]
    assert disagreement_seconds([(0, 1), (2, 3)], [(0.5, 2.5)]) == 2
    assert disagreement_seconds([(0, 1)], [(0, 1)]) == 0


@pytest.mark.parametrize("spans", [[{"start": -1, "end": 10}], [{"start": 0, "end": 20000}],
                                    [{"start": 5, "end": 5}],
                                    [{"start": 0, "end": 100}, {"start": 50, "end": 200}]])
def test_bad_vad_spans_rejected(spans):
    with pytest.raises(ValueError, match="timestamps"):
        sample_intervals(spans, samples=16000)


def test_audio_windows_not_padded_or_wrong_rate(tmp_path):
    pytest.importorskip("numpy")
    path = write_tone_wav(tmp_path / "tone.wav", [(0.2, 0.8)], duration=1)
    samples, pcm = read_window(path, 0, 1)
    assert len(samples) == 16000 and len(pcm) == 32000
    with pytest.raises(ValueError, match="Truncated"):
        read_window(path, 0, 2)
    with pytest.raises(ValueError, match="Invalid"):
        read_window(path, float("nan"), 1)
    wrong = write_tone_wav(tmp_path / "8k.wav", [], duration=1, rate=8000)
    with pytest.raises(ValueError, match="16 kHz"):
        read_window(wrong, 0, 1)


def test_audit_selection_has_no_duplicate_windows():
    predictions = [{"recording_id": "R", "question_id": f"W{i}", "actual": 0, "predicted": 1,
                    "score": i / 20} for i in range(20)]
    audit = select_audit(predictions)
    assert len(audit) == 10 and audit[("R", "W19")]["score"] == 19 / 20


@requires_ffmpeg
def test_paired_extraction_preserves_windows_and_blocks_changed_source(tmp_path):
    pytest.importorskip("sklearn")
    raw = tmp_path / "raw"; raw.mkdir()
    for person in range(6):
        for task, begin in (("NWS", 0.2), ("ST1", 0.4)):
            # Unique checksums for each genuine synthetic speaker/recording.
            offset = person * 0.01
            write_tone_wav(raw / f"ALL_{person+1:03d}_F_ENG_ENG_{task}.wav",
                           [(begin + offset, 0.9), (1.2 + offset, 1.8)], duration=2)
    base = tmp_path / "base"
    import_audio(raw, base, window_seconds=2, max_windows=1)
    class Detector:
        def detect(self, samples, *, start=0):
            return [(start + 0.1, start + 1.0)]
    class Prosody:
        def extract(self, samples):
            return dict.fromkeys(PROSODY_FEATURES, 0.1)
    out = tmp_path / "experiment"
    quality = extract_experiment(raw, base, out, detector=Detector(), prosody=Prosody())
    assert quality["status"] == "ok" and quality["windows"] == 12
    assert quality["human_audit_completed"] is False
    original = [json.loads(s) for s in (base / "features.jsonl").read_text().splitlines()]
    enriched = [json.loads(s) for s in (out / "features.jsonl").read_text().splitlines()]
    assert [r["recording_id"] for r in original] == [r["recording_id"] for r in enriched]
    assert all(r["features"].items() <= n["features"].items() for r, n in zip(original, enriched))
    # Reuse the same IDs but modify source audio: paired comparison must fail closed.
    write_tone_wav(raw / "ALL_001_F_ENG_ENG_NWS.wav", [], duration=2)
    partial = extract_experiment(raw, base, tmp_path / "changed", detector=Detector(), prosody=Prosody())
    assert partial["status"] == "partial" and len(partial["failures"]) == 1
    with pytest.raises(ValueError, match="Partial"):
        compare_models(tmp_path / "changed", tmp_path / "models")
    assert not (tmp_path / "models").exists()


def test_real_optional_extractors_silence(tmp_path):
    pytest.importorskip("silero_vad"); pytest.importorskip("opensmile")
    from interview_integrity.audio.research_vad import SileroDetector
    from interview_integrity.features.prosody import ProsodyExtractor
    path = write_tone_wav(tmp_path / "silence.wav", [], duration=1)
    samples, _ = read_window(path, 0, 1)
    assert SileroDetector().detect(samples) == []
    assert set(ProsodyExtractor().extract(samples)) == set(PROSODY_FEATURES)
