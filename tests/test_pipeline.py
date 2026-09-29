import json

import pytest

from interview_integrity.cli import main
from interview_integrity.datasets.io import load_jsonl, upsert_jsonl, write_csv
from interview_integrity.datasets.schema import InterviewSample, SchemaError
from interview_integrity.datasets.splits import assign_splits, find_group_leakage
from interview_integrity.pipeline import PipelineConfig, process_video
from interview_integrity.transcription import SidecarTranscriber

from .conftest import requires_ffmpeg


@requires_ffmpeg
def test_process_video_with_transcript(sample_video, metadata_dict, transcript_path, tmp_path):
    [sample] = process_video(
        sample_video, metadata_dict,
        transcriber=SidecarTranscriber(transcript_path),
        config=PipelineConfig(interim_dir=tmp_path),
    )
    row = sample.to_row()
    assert row["interview_id"] == "INT001"
    assert row["assistance_label"] == "HUMAN_UNASSISTED"
    assert row["deception_label"] == "UNKNOWN"
    assert row["answer_start"] == pytest.approx(0.5)
    assert row["answer_end"] == pytest.approx(3.5)
    assert row["answer_duration"] == pytest.approx(3.0)
    assert row["response_latency"] is None  # no question_end in metadata: not invented
    assert row["word_count"] == 13
    assert row["filler_word_count"] == 2
    assert row["pause_count"] == 1
    assert row["timing_source"] == "word_timestamps"
    assert (tmp_path / "INT001" / "transcript.json").is_file()


@requires_ffmpeg
def test_process_video_without_transcript_uses_vad(sample_video, metadata_dict, tmp_path):
    [sample] = process_video(sample_video, metadata_dict, config=PipelineConfig(interim_dir=tmp_path))
    row = sample.to_row()
    assert row["transcript"] is None
    assert row["word_count"] is None
    assert row["timing_source"] == "energy_vad"
    assert row["pause_count"] == 1
    assert row["speech_duration"] == pytest.approx(2.0, abs=0.15)


@requires_ffmpeg
def test_multi_question_with_windows(sample_video, transcript_path, tmp_path):
    meta = {
        "interview_id": "INT002", "participant_id": "P002", "source_dataset": "staged",
        "questions": [
            {"question_id": "Q1", "question_end": 0.2, "answer_start": 0.4, "answer_end": 1.8,
             "assistance_label": "HUMAN_UNASSISTED"},
            {"question_id": "Q2", "question_end": 2.0, "answer_start": 2.4, "answer_end": 3.8,
             "assistance_label": "AI_VERBATIM"},
        ],
    }
    s1, s2 = process_video(
        sample_video, meta, transcriber=SidecarTranscriber(transcript_path),
        config=PipelineConfig(interim_dir=tmp_path),
    )
    assert s1.transcript.startswith("Um, I think")
    assert s2.transcript == "You know, it catches bugs early."
    assert s1.response_latency == pytest.approx(0.2)
    assert s2.response_latency == pytest.approx(0.4)
    assert s2.assistance_label.value == "AI_VERBATIM"


@requires_ffmpeg
def test_multi_question_without_windows_fails(sample_video, tmp_path):
    meta = {
        "interview_id": "INT003", "participant_id": "P003", "source_dataset": "staged",
        "questions": [{"question_id": "Q1"}, {"question_id": "Q2"}],
    }
    with pytest.raises(SchemaError, match="answer_start"):
        process_video(sample_video, meta, config=PipelineConfig(interim_dir=tmp_path))


@requires_ffmpeg
def test_cli_process_writes_outputs(sample_video, transcript_path, tmp_path, capsys):
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(json.dumps({
        "interview_id": "INT001", "participant_id": "P001", "source_dataset": "staged", "question_id": "Q01",
    }))
    out_dir = tmp_path / "processed"
    args = ["process", "--video", str(sample_video), "--metadata", str(meta_path),
            "--transcript", str(transcript_path), "--interim-dir", str(tmp_path / "interim"),
            "--out-dir", str(out_dir)]
    assert main(args) == 0
    assert main(args) == 0  # re-running upserts instead of duplicating
    samples = load_jsonl(out_dir / "samples.jsonl")
    assert len(samples) == 1
    header = (out_dir / "samples.csv").read_text().splitlines()[0]
    assert header.startswith("interview_id,participant_id,question_id")
    assert "speech_rate_wpm" in header


def _sample(pid, rid, aug=None, q="Q1"):
    return InterviewSample(
        interview_id=rid, participant_id=pid, question_id=q, source_dataset="staged",
        recording_id=rid, augmentation=aug,
    ).validate()


def test_group_splits_keep_augmented_variants_together():
    samples = []
    for p in range(10):
        for aug in (None, "compress", "noise", "lowres"):
            samples.append(_sample(f"P{p:02d}", f"R{p:02d}", aug))
    split = assign_splits(samples, seed=1)
    assert find_group_leakage(split) == {}
    assert find_group_leakage(split, "recording_id") == {}
    assert {s.split for s in split} == {"train", "val", "test"}


def test_leakage_detector_flags_mixed_groups():
    a = _sample("P1", "R1")
    b = _sample("P1", "R1", "noise")
    a.split, b.split = "train", "test"
    assert find_group_leakage([a, b]) == {"P1": {"train", "test"}}


def test_upsert_and_csv_handle_nulls(tmp_path):
    s = _sample("P1", "R1")
    s.features = {"word_count": None}
    all_samples = upsert_jsonl([s], tmp_path / "s.jsonl")
    write_csv(all_samples, tmp_path / "s.csv")
    assert load_jsonl(tmp_path / "s.jsonl")[0].features["word_count"] is None
