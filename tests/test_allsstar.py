import json
import zipfile

import pytest

from interview_integrity.modeling.allsstar import import_audio, inventory, parse_recording
from interview_integrity.modeling.audio_baseline import prepare_data
from .conftest import requires_ffmpeg, write_tone_wav


def test_parse_labels_and_stable_speaker():
    read = parse_recording("ALL_CCT_ENG_NWS/ALL_073_M_CCT_ENG_NWS.wav", "source")
    spontaneous = parse_recording("ALL_073_M_CCT_ENG_ST1.wav", "source")
    assert read.participant_id == spontaneous.participant_id == "ALLSSTAR:073"
    assert read.delivery_label == "READING"
    assert spontaneous.delivery_label == "SPONTANEOUS"


@pytest.mark.parametrize("name", ["bad.wav", "ALL_073_M_CCT_CCT_NWS.wav",
                                 "ALL_073_M_CCT_ENG_FAKE.wav",
                                 "ALL_CCT_ENG_ST1/ALL_073_M_CCT_ENG_NWS.wav"])
def test_reject_ambiguous_labels(name):
    with pytest.raises(ValueError):
        parse_recording(name, "source")


def test_inventory_no_synthetic_counts(tmp_path):
    (tmp_path / "ALL_001_F_ENG_ENG_NWS.wav").touch()
    (tmp_path / "ALL_001_F_ENG_ENG_ST1.wav").touch()
    (tmp_path / "ALL_001_F_ENG_ENG_ST1.TextGrid").touch()
    recordings, counts = inventory(tmp_path)
    assert len(recordings) == 2
    assert counts["participants"] == 1
    assert counts["textgrid_files"] == 1


@pytest.mark.parametrize("member", ["../escape.wav", "/escape.wav", "C:/escape.wav", "a\\escape.wav"])
def test_unsafe_zip_rejected(tmp_path, member):
    source = tmp_path / "bad.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(member, b"data")
    with pytest.raises(ValueError, match="Unsafe"):
        inventory(source)
    assert not (tmp_path / "escape.wav").exists()


def test_duplicate_wav_and_conflicting_speaker(tmp_path):
    (tmp_path / "ALL_001_F_ENG_ENG_NWS.wav").touch()
    duplicate = tmp_path / "nested"
    duplicate.mkdir()
    (duplicate / "ALL_001_F_ENG_ENG_NWS.wav").touch()
    with pytest.raises(ValueError, match="Duplicate recording"):
        inventory(tmp_path)
    (duplicate / "ALL_001_F_ENG_ENG_NWS.wav").unlink()
    (tmp_path / "ALL_001_F_CCT_ENG_ST1.wav").touch()
    with pytest.raises(ValueError, match="inconsistent"):
        inventory(tmp_path)


def test_expected_inventory_fails_before_output(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    (raw / "ALL_001_F_ENG_ENG_NWS.wav").touch()
    with pytest.raises(ValueError, match="expected 1163"):
        import_audio(raw, tmp_path / "out", expected_wav=1163)
    assert not (tmp_path / "out").exists()


def test_refuse_qna_and_invalid_window(tmp_path):
    with pytest.raises(ValueError, match="candidate-only"):
        import_audio(tmp_path, tmp_path / "out", tasks=("NWS", "QNA"))
    with pytest.raises(ValueError, match="Window"):
        import_audio(tmp_path, tmp_path / "out", window_seconds=float("nan"))


@requires_ffmpeg
def test_fixed_windows_join_ground_truth_from_zip(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    # Different fixture hashes intentionally; these tones do not validate delivery detection.
    for task, segments in [("NWS", [(0.2, 0.9), (1.2, 1.9), (2.2, 2.9), (3.2, 3.9)]),
                           ("ST1", [(0.4, 0.9), (1.4, 1.9), (2.4, 2.9), (3.4, 3.9)])]:
        write_tone_wav(raw / f"ALL_001_F_ENG_ENG_{task}.wav", segments, duration=4)
    archive_path = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in raw.iterdir():
            archive.write(path, arcname=path.name)
    report = import_audio(archive_path, tmp_path / "out", tasks=("NWS", "ST1"),
                          window_seconds=2, max_windows=2, expected_wav=2, expected_participants=1)
    assert report["status"] == "ok"
    assert report["windows"] == 4
    assert report["complete_archive_crc_verified"] is True
    rows = [json.loads(line) for line in (tmp_path / "out/features.jsonl").read_text().splitlines()]
    import csv
    with (tmp_path / "out/labels.csv").open() as stream:
        labels = list(csv.DictReader(stream))
    x, y, groups, _, _ = prepare_data(rows, labels)
    assert len(x) == 4 and set(y) == {0, 1} and set(groups) == {"ALLSSTAR:001"}
    assert all(row["window_end"] - row["window_start"] == 2 for row in rows)
    with pytest.raises(ValueError, match="exists"):
        import_audio(archive_path, tmp_path / "out")


@requires_ffmpeg
def test_silent_sources_do_not_become_training_rows(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    for task in ("NWS", "ST1"):
        write_tone_wav(raw / f"ALL_001_F_ENG_ENG_{task}.wav", [], duration=2)
    report = import_audio(raw, tmp_path / "out", window_seconds=2)
    assert report["status"] == "failed" and report["windows"] == 0
    assert len(report["excluded"]) == 2


def test_decode_errors_are_not_success(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    for task in ("NWS", "ST1"):
        (raw / f"ALL_001_F_ENG_ENG_{task}.wav").write_bytes(b"not audio")
    report = import_audio(raw, tmp_path / "out", window_seconds=2)
    assert report["status"] == "failed" and len(report["failures"]) == 2
