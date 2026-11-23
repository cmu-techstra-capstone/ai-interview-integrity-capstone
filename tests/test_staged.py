"""Staged-interview support: schema fields, AI metadata, multi-question flow."""

import json

import pytest

from interview_integrity.datasets.schema import InterviewSample, RecordingMetadata, SchemaError
from interview_integrity.pipeline import PipelineConfig, process_video
from interview_integrity.storage.manifest import ManifestEntry
from interview_integrity.storage.remote import LocalFolderStorage
from interview_integrity.storage.workflow import process_manifest_entry, processed_paths
from interview_integrity.transcription import SidecarTranscriber

from .conftest import requires_ffmpeg

STAGED = {
    "interview_id": "STG001",
    "participant_id": "P010",
    "source_dataset": "staged",
    "questions": [
        {
            "question_id": "Q1", "question_text": "Why does testing matter?",
            "question_start": 0.0, "question_end": 0.2, "answer_start": 0.4, "answer_end": 1.8,
            "assistance_label": "HUMAN_UNASSISTED",
        },
        {
            "question_id": "Q2", "question_text": "How do you catch bugs early?",
            "question_start": 1.9, "question_end": 2.2, "answer_start": 2.4, "answer_end": 3.8,
            "assistance_label": "AI_VERBATIM",
            "ai_model_used": "example-model-1", "ai_prompt_used": "Answer briefly: How do you catch bugs early?",
            "generated_ai_answer": "You know, it catches bugs early.", "response_notes": "Read from second screen.",
        },
    ],
}


def test_staged_metadata_parses_all_fields():
    meta = RecordingMetadata.from_dict(STAGED)
    q1, q2 = meta.questions
    assert q1.ai_model_used is None and q1.generated_ai_answer is None  # not required for human answers
    assert q2.question_start == 1.9 and q2.ai_model_used == "example-model-1"
    assert q2.response_notes == "Read from second screen."


def test_question_window_validated():
    bad = {**STAGED, "questions": [{"question_id": "Q1", "question_start": 5, "question_end": 2}]}
    with pytest.raises(SchemaError, match="question_end"):
        RecordingMetadata.from_dict(bad)


def test_blank_ai_fields_become_null():
    meta = RecordingMetadata.from_dict({**STAGED, "questions": [{"question_id": "Q1", "ai_model_used": "  "}]})
    assert meta.questions[0].ai_model_used is None


def test_legacy_path_columns_still_load():
    row = InterviewSample(interview_id="I", participant_id="P", question_id="Q",
                          source_dataset="staged").validate().to_row()
    row.pop("video_reference"); row.pop("audio_reference")
    row.update(video_path="old/video.mp4", audio_path="old/audio.wav")
    sample = InterviewSample.from_row(row)
    assert sample.video_reference == "old/video.mp4" and sample.audio_reference == "old/audio.wav"
    assert "video_path" not in sample.features


@requires_ffmpeg
def test_staged_recording_flows_through_pipeline(sample_video, transcript_path, tmp_path):
    s1, s2 = process_video(sample_video, STAGED, transcriber=SidecarTranscriber(transcript_path),
                           config=PipelineConfig(interim_dir=tmp_path))
    assert (s1.assistance_label.value, s2.assistance_label.value) == ("HUMAN_UNASSISTED", "AI_VERBATIM")
    assert s1.ai_model_used is None
    assert s2.generated_ai_answer == "You know, it catches bugs early."
    assert s2.question_start == 1.9 and s2.response_latency == pytest.approx(0.2)
    assert s1.video_sha256 and len(s1.video_sha256) == 64
    row = s2.to_row()
    for col in ("question_start", "ai_model_used", "ai_prompt_used", "generated_ai_answer", "response_notes",
                "video_reference", "audio_reference"):
        assert col in row


@requires_ffmpeg
def test_staged_manifest_with_metadata_file(sample_video, transcript_path, tmp_path):
    root = tmp_path / "shared"
    root.mkdir()
    storage = LocalFolderStorage(root)
    storage.upload(sample_video, "datasets/staged_interviews/STG001.mp4")
    storage.upload(transcript_path, "datasets/staged_interviews/STG001.transcript.json")
    (tmp_path / "m.json").write_text(json.dumps(STAGED))
    storage.upload(tmp_path / "m.json", "metadata/staged_interviews/STG001.json")
    entry = ManifestEntry(
        dataset_name="staged_interviews", video_id="STG001", source_dataset="staged", participant_id="P010",
        drive_location="datasets/staged_interviews/STG001.mp4",
        transcript_location="datasets/staged_interviews/STG001.transcript.json",
        metadata_location="metadata/staged_interviews/STG001.json", file_status="IN_DRIVE",
    ).validate()

    samples = process_manifest_entry(entry, storage, cache_root=tmp_path / "cache")

    assert [s.question_id for s in samples] == ["Q1", "Q2"]
    for q in ("Q1", "Q2"):
        assert storage.exists(processed_paths(entry, q)["combined"])
    assert storage.exists(processed_paths(entry)["transcript"])
    combined = json.loads((root / processed_paths(entry, "Q2")["combined"]).read_text())
    assert combined["ai_model_used"] == "example-model-1"
    assert entry.file_status == "PROCESSED"
    assert list((tmp_path / "cache").iterdir()) == []


@requires_ffmpeg
def test_staged_manifest_participant_mismatch_rejected(sample_video, tmp_path):
    root = tmp_path / "shared"
    root.mkdir()
    storage = LocalFolderStorage(root)
    storage.upload(sample_video, "datasets/staged_interviews/STG001.mp4")
    (tmp_path / "m.json").write_text(json.dumps(STAGED))
    storage.upload(tmp_path / "m.json", "metadata/STG001.json")
    entry = ManifestEntry(dataset_name="staged_interviews", video_id="STG001", source_dataset="staged",
                          participant_id="P999", drive_location="datasets/staged_interviews/STG001.mp4",
                          metadata_location="metadata/STG001.json")
    with pytest.raises(SchemaError, match="participant_id"):
        process_manifest_entry(entry, storage, cache_root=tmp_path / "cache")
