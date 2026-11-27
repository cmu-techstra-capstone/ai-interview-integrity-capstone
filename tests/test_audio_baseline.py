"""Synthetic fixtures test the training machinery, not real detector accuracy."""
import pytest

from interview_integrity.modeling.audio_baseline import AUDIO_FEATURES, prepare_data, train_baseline


def fixtures():
    rows, labels = [], []
    for person in range(6):
        for delivery in ("READING", "SPONTANEOUS"):
            recording = f"P{person}-{delivery}"
            rows.append({"recording_id": recording, "question_id": "Q1", "participant_id": f"P{person}",
                         "pause_ratio": 0.1 if delivery == "READING" else 0.4,
                         "audio_snr_db": 20, "word_count": 100, "video_sha256": recording})
            labels.append({"recording_id": recording, "question_id": "Q1", "participant_id": f"P{person}",
                           "delivery_label": delivery, "label_source": "controlled_protocol"})
    return rows, labels


def test_default_features_are_audio_only():
    rows, labels = fixtures()
    x, y, groups, keys, names = prepare_data(rows, labels)
    assert names == AUDIO_FEATURES and len(x) == 12
    assert "audio_snr_db" not in names and "word_count" not in names
    assert "speech_rate_wpm" not in names


@pytest.mark.parametrize("field,value,match", [
    ("delivery_label", "DECEPTIVE", "delivery_label"),
    ("participant_id", "unknown:clip", "participant IDs"),
    ("label_source", "guessed_from_fluency", "label_source"),
])
def test_unsupported_labels_and_groups_rejected(field, value, match):
    rows, labels = fixtures()
    labels[0][field] = value
    with pytest.raises(ValueError, match=match): prepare_data(rows, labels)


def test_duplicate_labels_rejected():
    rows, labels = fixtures()
    with pytest.raises(ValueError, match="Duplicate label"):
        prepare_data(rows, labels + [labels[0]])


def test_shared_media_across_people_rejected():
    rows, labels = fixtures()
    rows[2]["video_sha256"] = rows[0]["video_sha256"]
    with pytest.raises(ValueError, match="multiple participants"):
        prepare_data(rows, labels)


def test_grouped_training_and_missing_values():
    pytest.importorskip("sklearn")
    rows, labels = fixtures()
    bundle, report = train_baseline(rows, labels)
    assert all(fold["participant_overlap"] == 0 for fold in report["folds"])
    assert report["rows"] == 12 and report["participants"] == 6
    assert report["target"] == "READING_vs_SPONTANEOUS"
    assert bundle["pipeline"] is not None
    assert "oof_metrics" in report and "dummy_balanced_accuracy" in report["oof_metrics"]


def test_too_few_participants_rejected():
    pytest.importorskip("sklearn")
    rows, labels = fixtures()
    with pytest.raises(ValueError, match="distinct participants"):
        train_baseline(rows[:2], labels[:2])
