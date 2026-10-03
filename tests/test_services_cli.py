"""Application layer, configuration, staged tooling and housekeeping (lightweight)."""

import json
import os
import shutil
import time

import pytest

from interview_integrity import services
from interview_integrity.cli import build_parser, main
from interview_integrity.config import ConfigError, Settings
from interview_integrity.storage.cache import purge_stale_caches
from interview_integrity.storage.manifest import ManifestEntry, load_manifest, save_manifest
from interview_integrity.storage.remote import LocalFolderStorage

from .conftest import requires_ffmpeg

STAGED_META = {
    "interview_id": "STG-P001-S01", "participant_id": "P001", "source_dataset": "staged",
    "questions": [
        {"question_id": "Q01", "assistance_label": "HUMAN_UNASSISTED"},
        {"question_id": "Q02", "assistance_label": "AI_VERBATIM"},
    ],
}


# ---------------------------------------------------------------- config

def test_settings_defaults_and_env():
    assert Settings.from_env({}).max_cache_mb == 500
    s = Settings.from_env({"INTERVIEW_INTEGRITY_MAX_CACHE_MB": "64", "INTERVIEW_INTEGRITY_SHARED_ROOT": "/mnt/x",
                           "INTERVIEW_INTEGRITY_LOG_LEVEL": "debug", "INTERVIEW_INTEGRITY_OUT_DIR": "out"})
    assert s.max_cache_mb == 64 and str(s.shared_root) == "/mnt/x" and s.log_level == "DEBUG"
    assert str(s.out_dir) == "out"


@pytest.mark.parametrize("env", [{"INTERVIEW_INTEGRITY_MAX_CACHE_MB": "lots"},
                                 {"INTERVIEW_INTEGRITY_MAX_CACHE_MB": "-1"},
                                 {"INTERVIEW_INTEGRITY_LOG_LEVEL": "LOUD"}])
def test_settings_invalid(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_cli_defaults_come_from_settings():
    parser = build_parser(Settings(max_cache_mb=42, shared_root=None))
    args = parser.parse_args(["process-remote", "--dataset", "d", "--root", "/r"])
    assert args.max_cache_mb == 42


def test_cli_is_thin_wrapper():
    import inspect
    from interview_integrity import cli

    src = inspect.getsource(cli)
    for heavy in ("process_video(", "load_manifest(", "upsert_jsonl(", "check_dataset("):
        assert heavy not in src, f"cli.py should delegate {heavy} to services"


# ---------------------------------------------------------------- cache housekeeping

def test_purge_stale_caches_only_touches_old_cache_dirs(tmp_path):
    old, fresh, other = tmp_path / "iic-cache-old", tmp_path / "iic-cache-new", tmp_path / "keep-me"
    for d in (old, fresh, other):
        d.mkdir()
        (d / "f").write_text("x")
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))
    os.utime(other, (past, past))
    assert purge_stale_caches(tmp_path, older_than_hours=12) == [old]
    assert fresh.exists() and other.exists() and not old.exists()


def test_cache_clean_cli(tmp_path):
    assert main(["cache-clean", "--cache-dir", str(tmp_path)]) == 0


# ---------------------------------------------------------------- staged tooling

def test_staged_template_and_validate(tmp_path):
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps([{"question_id": "Q01", "question_text": "A?"}, {"question_id": "Q02", "question_text": "B?"}]))
    out = tmp_path / "m.json"
    assert main(["staged", "template", "--interview-id", "STG-P001-S01", "--participant-id", "P001",
                 "--question-bank", str(bank), "--condition", "Q01=HUMAN_UNASSISTED", "--condition", "Q02=ai_verbatim",
                 "--out", str(out)]) == 0
    meta = json.loads(out.read_text())
    assert [q["assistance_label"] for q in meta["questions"]] == ["HUMAN_UNASSISTED", "AI_VERBATIM"]
    assert meta["questions"][1]["ai_model_used"] is None
    # multi-question recording without answer windows -> validation error
    assert main(["staged", "validate", str(out)]) == 1
    with pytest.raises(FileExistsError):
        services.staged_template("STG-P001-S01", "P001", bank, out_path=out)


def test_import_labels_fills_timestamps_and_passes_validation(tmp_path):
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps(STAGED_META))
    labels = tmp_path / "labels.txt"
    labels.write_text("1.0\t4.5\tQ01 question\n5.2\t30.0\tQ01 answer\n31.0\t34.0\tQ02-question\n"
                      "35.5\t60.0\tq02_answer\n")
    assert main(["staged", "import-labels", "--metadata", str(meta), "--labels", str(labels)]) == 0
    q1, q2 = json.loads(meta.read_text())["questions"]
    assert (q1["question_start"], q1["question_end"], q1["answer_start"], q1["answer_end"]) == (1.0, 4.5, 5.2, 30.0)
    assert q2["answer_start"] == 35.5
    codes = {i.code for i in services.staged_validate(meta)}
    assert "MISSING_ANSWER_WINDOW" not in codes and "MISSING_AI_METADATA" in codes  # Q02 lacks AI metadata
    assert not any(i.severity == "error" for i in services.staged_validate(meta))


@pytest.mark.parametrize("content,match", [
    ("1.0\t2.0\n", "start<TAB>end<TAB>label"),
    ("x\t2.0\tQ01 answer\n", "numbers"),
    ("1.0\t2.0\tQ01 intro\n", "must look like"),
    ("3.0\t2.0\tQ01 answer\n", "before start"),
    ("1.0\t2.0\tQ01 answer\n3.0\t4.0\tQ01 answer\n", "duplicate"),
    ("1.0\t2.0\tQ01 answer\n3.0\t4.0\tq01 answer\n", "duplicate"),
    ("1.0\t2.0\tQ09 answer\n", "not in the metadata"),
])
def test_bad_label_files_rejected(tmp_path, content, match):
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps(STAGED_META))
    labels = tmp_path / "l.txt"
    labels.write_text(content)
    with pytest.raises(Exception, match=match):
        services.staged_import_labels(meta, labels)


def test_staged_validate_catches_protocol_problems(tmp_path):
    bad = {**STAGED_META, "participant_id": "alice", "questions": [
        {"question_id": "Q01", "assistance_label": "HUMAN_UNASSISTED", "answer_start": 1, "answer_end": 10,
         "ai_model_used": "x"},
        {"question_id": "Q02", "assistance_label": None, "answer_start": 5, "answer_end": 20},
    ]}
    path = tmp_path / "m.json"
    path.write_text(json.dumps(bad))
    codes = {i.code for i in services.staged_validate(path)}
    assert {"ID_CONVENTION", "MISSING_ASSISTANCE_LABEL", "AI_METADATA_ON_HUMAN_ANSWER"} <= codes


def test_staged_validate_overlapping_answers(tmp_path):
    meta = {**STAGED_META, "questions": [
        {"question_id": "Q01", "assistance_label": "HUMAN_UNASSISTED", "answer_start": 1, "answer_end": 10},
        {"question_id": "Q02", "assistance_label": "HUMAN_UNASSISTED", "answer_start": 5, "answer_end": 20},
    ]}
    path = tmp_path / "m.json"
    path.write_text(json.dumps(meta))
    assert "OVERLAPPING_ANSWERS" in {i.code for i in services.staged_validate(path)}


# ---------------------------------------------------------------- batch / remote processing

@requires_ffmpeg
def test_process_batch_continues_after_failures(sample_video, transcript_path, tmp_path):
    batch = tmp_path / "batch"
    batch.mkdir()
    shutil.copy(sample_video, batch / "rec1.mp4")
    shutil.copy(transcript_path, batch / "rec1.transcript.json")
    (batch / "rec1.metadata.json").write_text(json.dumps({
        "interview_id": "STG-P001-S01", "participant_id": "P001", "source_dataset": "staged",
        "question_id": "Q01", "assistance_label": "HUMAN_UNASSISTED"}))
    (batch / "rec2.metadata.json").write_text(json.dumps({  # no video
        "interview_id": "STG-P002-S01", "participant_id": "P002", "source_dataset": "staged", "question_id": "Q01"}))
    shutil.copy(sample_video, batch / "rec3.mp4")
    (batch / "rec3.metadata.json").write_text(json.dumps({  # timestamps beyond the recording
        "interview_id": "STG-P003-S01", "participant_id": "P003", "source_dataset": "staged", "question_id": "Q01",
        "assistance_label": "HUMAN_UNASSISTED", "answer_start": 1, "answer_end": 99}))
    out = tmp_path / "out"
    rc = main(["process-batch", "--dir", str(batch), "--out-dir", str(out), "--interim-dir", str(tmp_path / "i")])
    assert rc == 1
    report = json.loads((out / "batch_quality_report.json").read_text())
    assert set(report["failed_recordings"]) == {"rec2", "rec3"}
    assert report["samples"] == 1
    assert (out / "samples.jsonl").read_text().count("\n") == 1


# --- regression: process-remote used to abort on the first failing recording, losing the
# rows already processed and leaving the failed entry's status unchanged.
@requires_ffmpeg
def test_process_remote_records_failures_and_keeps_going(sample_video, tmp_path):
    root = tmp_path / "shared"
    root.mkdir()
    storage = LocalFolderStorage(root)
    storage.upload(sample_video, "datasets/staged_interviews/ok.mp4")
    (tmp_path / "bad.json").write_text(json.dumps({**STAGED_META, "participant_id": "P001"}))  # 2 q, no windows
    storage.upload(tmp_path / "bad.json", "metadata/bad.json")
    storage.upload(sample_video, "datasets/staged_interviews/bad.mp4")
    manifest_dir = tmp_path / "manifests"
    entries = [
        ManifestEntry(dataset_name="staged_interviews", video_id="bad", source_dataset="staged", participant_id="P001",
                      drive_location="datasets/staged_interviews/bad.mp4", metadata_location="metadata/bad.json",
                      file_status="IN_DRIVE"),
        ManifestEntry(dataset_name="staged_interviews", video_id="ok", source_dataset="staged", participant_id="P002",
                      question_id="Q01", assistance_label="HUMAN_UNASSISTED",
                      drive_location="datasets/staged_interviews/ok.mp4", file_status="IN_DRIVE"),
    ]
    save_manifest(entries, manifest_dir / "files" / "staged_interviews.csv")
    result = services.process_from_storage("staged_interviews", root, manifest_dir=manifest_dir,
                                           cache_dir=tmp_path / "cache", out_dir=tmp_path / "out")
    assert result.processed == ["ok"] and set(result.failed) == {"bad"}
    status = {e.video_id: e.file_status for e in load_manifest(manifest_dir / "files" / "staged_interviews.csv")}
    assert status == {"bad": "ERROR", "ok": "PROCESSED"}
    assert result.dataset_rows == 1
    assert list((tmp_path / "cache").iterdir()) == []
