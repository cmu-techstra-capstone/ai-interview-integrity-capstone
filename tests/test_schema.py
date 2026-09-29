import pytest

from interview_integrity.datasets.schema import (
    AssistanceLabel,
    DeceptionLabel,
    InterviewSample,
    RecordingMetadata,
    SchemaError,
    SourceDataset,
)


def test_single_answer_metadata(metadata_dict):
    meta = RecordingMetadata.from_dict(metadata_dict)
    assert meta.recording_id == "INT001"
    assert len(meta.questions) == 1
    q = meta.questions[0]
    assert q.question_id == "Q01"
    assert q.assistance_label is AssistanceLabel.HUMAN_UNASSISTED
    assert q.deception_label is DeceptionLabel.UNKNOWN


def test_missing_labels_default_to_unknown():
    meta = RecordingMetadata.from_dict(
        {"interview_id": "I", "participant_id": "P", "source_dataset": "staged", "question_id": "Q"}
    )
    assert meta.questions[0].assistance_label is AssistanceLabel.UNKNOWN
    assert meta.questions[0].deception_label is DeceptionLabel.UNKNOWN


def test_labels_are_case_insensitive():
    meta = RecordingMetadata.from_dict({
        "interview_id": "I", "participant_id": "P", "source_dataset": "STAGED",
        "question_id": "Q", "assistance_label": "ai_verbatim",
    })
    assert meta.questions[0].assistance_label is AssistanceLabel.AI_VERBATIM


def test_multi_question_metadata_inherits_defaults():
    meta = RecordingMetadata.from_dict({
        "interview_id": "I", "participant_id": "P", "source_dataset": "staged",
        "assistance_label": "AI_ASSISTED",
        "questions": [
            {"question_id": "Q1", "answer_start": 1, "answer_end": 5},
            {"question_id": "Q2", "answer_start": 6, "answer_end": 9, "assistance_label": "HUMAN_UNASSISTED"},
        ],
    })
    assert [q.assistance_label for q in meta.questions] == [
        AssistanceLabel.AI_ASSISTED, AssistanceLabel.HUMAN_UNASSISTED
    ]


@pytest.mark.parametrize("missing", ["interview_id", "participant_id", "source_dataset", "question_id"])
def test_missing_required_field(metadata_dict, missing):
    del metadata_dict[missing]
    with pytest.raises(SchemaError, match=missing):
        RecordingMetadata.from_dict(metadata_dict)


def test_invalid_label(metadata_dict):
    metadata_dict["assistance_label"] = "CHEATING"
    with pytest.raises(SchemaError, match="assistance_label"):
        RecordingMetadata.from_dict(metadata_dict)


def test_invalid_answer_window(metadata_dict):
    metadata_dict.update(answer_start=5, answer_end=2)
    with pytest.raises(SchemaError, match="answer_end"):
        RecordingMetadata.from_dict(metadata_dict)


def test_negative_time_rejected(metadata_dict):
    metadata_dict["question_end"] = -1
    with pytest.raises(SchemaError):
        RecordingMetadata.from_dict(metadata_dict)


def test_duplicate_question_ids():
    with pytest.raises(SchemaError, match="Duplicate"):
        RecordingMetadata.from_dict({
            "interview_id": "I", "participant_id": "P", "source_dataset": "staged",
            "questions": [{"question_id": "Q1"}, {"question_id": "Q1"}],
        })


@pytest.mark.parametrize("source", ["dolos", "real_life_deception", "bag_of_lies"])
def test_deception_datasets_cannot_carry_assistance_labels(source):
    with pytest.raises(SchemaError, match="deception labels only"):
        RecordingMetadata.from_dict({
            "interview_id": "I", "participant_id": "P", "source_dataset": source,
            "question_id": "Q", "deception_label": "DECEPTIVE", "assistance_label": "AI_ASSISTED",
        })


def test_deception_dataset_keeps_deception_label_only():
    meta = RecordingMetadata.from_dict({
        "interview_id": "I", "participant_id": "P", "source_dataset": "dolos",
        "question_id": "Q", "deception_label": "DECEPTIVE",
    })
    q = meta.questions[0]
    assert q.deception_label is DeceptionLabel.DECEPTIVE
    assert q.assistance_label is AssistanceLabel.UNKNOWN


def test_sample_row_roundtrip():
    sample = InterviewSample(
        interview_id="I", participant_id="P", question_id="Q", source_dataset=SourceDataset.STAGED,
        assistance_label=AssistanceLabel.AI_PERSONALIZED, transcript="hello",
        answer_start=1.0, answer_end=2.5, answer_duration=1.5,
        features={"word_count": 1, "speech_rate_wpm": None},
    ).validate()
    row = sample.to_row()
    assert row["assistance_label"] == "AI_PERSONALIZED"
    assert row["response_latency"] is None
    assert row["speech_rate_wpm"] is None
    assert InterviewSample.from_row(row) == sample


def test_feature_name_collision_rejected():
    sample = InterviewSample(
        interview_id="I", participant_id="P", question_id="Q", source_dataset="staged",
        features={"transcript": "oops"},
    )
    with pytest.raises(SchemaError, match="collide"):
        sample.validate()
