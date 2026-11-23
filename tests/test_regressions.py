"""Regression tests for backend bugs found during hardening (one test per bug)."""

import pytest

from interview_integrity.datasets.io import load_jsonl, upsert_jsonl, write_csv, write_jsonl
from interview_integrity.datasets.quality import check_dataset, check_sample
from interview_integrity.datasets.schema import InterviewSample, SchemaError
from interview_integrity.datasets.splits import assign_splits, find_group_leakage, leakage_groups
from interview_integrity.pipeline import PipelineConfig, process_video
from interview_integrity.storage.manifest import ManifestEntry, load_manifest, save_manifest

from .conftest import requires_ffmpeg


def _s(**kw):
    base = dict(interview_id="I1", participant_id="P1", question_id="Q1", source_dataset="staged")
    return InterviewSample(**{**base, **kw})


# --- Bug: a row with a non-serializable feature value wiped the whole samples.jsonl
def test_bad_feature_value_cannot_wipe_dataset(tmp_path):
    path = tmp_path / "samples.jsonl"
    write_jsonl([_s(question_id=f"Q{i}").validate() for i in range(5)], path)
    bad = _s(question_id="Q0", features={"plugin_val": {1, 2}})
    with pytest.raises(SchemaError, match="plugin_val"):
        upsert_jsonl([bad.validate()], path)
    assert len(load_jsonl(path)) == 5


def test_write_failure_leaves_previous_file_intact(tmp_path):
    path = tmp_path / "samples.jsonl"
    write_jsonl([_s().validate()], path)
    unvalidated = _s(question_id="Q2", features={"x": float("nan")})  # bypasses validate()
    with pytest.raises(ValueError):
        write_jsonl([_s().validate(), unvalidated], path)
    assert len(load_jsonl(path)) == 1
    assert not list(tmp_path.glob(".samples.jsonl.*"))  # no temp files left behind


@pytest.mark.parametrize("value", [[1, 2], {"a": 1}, float("inf"), object()])
def test_non_scalar_feature_values_rejected(value):
    with pytest.raises(SchemaError):
        _s(features={"f": value}).validate()


def test_csv_write_is_atomic(tmp_path):
    path = tmp_path / "s.csv"
    write_csv([_s().validate()], path)
    before = path.read_text()

    class Boom:
        def to_row(self):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        write_csv([_s().validate(), Boom()], path)
    assert path.read_text() == before


# --- Bug: one invalid manifest entry truncated the manifest file
def test_invalid_manifest_entry_does_not_truncate_file(tmp_path):
    path = tmp_path / "m.csv"
    good = [ManifestEntry(dataset_name="d", video_id=f"v{i}", source_dataset="staged") for i in range(3)]
    save_manifest(good, path)
    bad = ManifestEntry(dataset_name="d", video_id="vx", source_dataset="not_a_dataset")
    with pytest.raises(SchemaError):
        save_manifest([*good, bad], path)
    assert [e.video_id for e in load_manifest(path)] == ["v0", "v1", "v2"]


# --- Bug: answer windows beyond the end of the recording were accepted silently
@requires_ffmpeg
def test_answer_window_beyond_recording_rejected(sample_video, metadata_dict, tmp_path):
    with pytest.raises(SchemaError, match="beyond the recording"):
        process_video(sample_video, {**metadata_dict, "answer_start": 1.0, "answer_end": 30.0},
                      config=PipelineConfig(interim_dir=tmp_path))


@requires_ffmpeg
def test_question_end_after_answer_end_rejected(sample_video, metadata_dict, tmp_path):
    with pytest.raises(SchemaError, match="after answer_end"):
        process_video(sample_video, {**metadata_dict, "question_end": 3.0, "answer_start": 0.5, "answer_end": 2.0},
                      config=PipelineConfig(interim_dir=tmp_path))


def test_quality_flags_impossible_timing_in_existing_rows():
    s = _s(answer_start=1.0, answer_end=30.0, answer_duration=29.0, features={"audio_duration": 4.0}).validate()
    assert "IMPOSSIBLE_TIMING" in [i.code for i in check_sample(s)]


# --- Bug: rows of one recording with inconsistent participant_ids could land in different splits
def test_recording_never_split_even_with_inconsistent_participant_ids():
    for seed in range(50):
        rows = [_s(interview_id=f"R{i}", recording_id=f"R{i}", participant_id=f"P{i}").validate() for i in range(20)]
        rows.append(_s(interview_id="R0", recording_id="R0", participant_id="P0-typo", question_id="Q2").validate())
        out = assign_splits(rows, seed=seed)
        assert find_group_leakage(out, "recording_id") == {}


def test_same_source_video_grouped_across_ids():
    a = _s(interview_id="A", recording_id="A", participant_id="P1", video_sha256="ab" * 32).validate()
    b = _s(interview_id="B", recording_id="B", participant_id="P2", video_sha256="ab" * 32).validate()
    c = _s(interview_id="C", recording_id="C", participant_id="P3").validate()
    g = leakage_groups([a, b, c])
    assert g[0] == g[1] != g[2]


def test_quality_reports_inconsistent_participant():
    rows = [_s(recording_id="R1").validate(), _s(recording_id="R1", participant_id="P9", question_id="Q2").validate()]
    assert "INCONSISTENT_PARTICIPANT" in [i.code for i in check_dataset(rows)]
