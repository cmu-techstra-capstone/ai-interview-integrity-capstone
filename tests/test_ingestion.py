import json

import pytest

from interview_integrity.datasets.schema import SchemaError
from interview_integrity.ingestion.video import ingest_video, probe_video, sha256sum
from interview_integrity.media import InvalidMediaError, NoAudioStreamError

from .conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


def test_probe_video(sample_video):
    info = probe_video(sample_video)
    assert info.width == 160 and info.height == 120
    assert info.fps == pytest.approx(10.0)
    assert info.duration == pytest.approx(4.0, abs=0.1)
    assert info.has_audio
    assert len(info.sha256) == 64


def test_ingest_creates_audio_and_manifest(sample_video, metadata_dict, tmp_path):
    before = sha256sum(sample_video)
    ingested = ingest_video(sample_video, metadata_dict, tmp_path)

    assert ingested.work_dir == tmp_path / "INT001"
    assert (ingested.work_dir / "audio.wav").is_file()
    manifest = json.loads(ingested.manifest_path.read_text())
    assert manifest["metadata"]["participant_id"] == "P001"
    assert manifest["video"]["sha256"] == before
    # The original video is preserved untouched.
    assert sha256sum(sample_video) == before


def test_augmented_variant_gets_own_work_dir(sample_video, metadata_dict, tmp_path):
    metadata_dict["augmentation"] = "compress_low"
    ingested = ingest_video(sample_video, metadata_dict, tmp_path)
    assert ingested.work_dir.name == "INT001__compress_low"
    assert ingested.metadata.recording_id == "INT001"


def test_missing_video(tmp_path, metadata_dict):
    with pytest.raises(FileNotFoundError):
        ingest_video(tmp_path / "nope.mp4", metadata_dict, tmp_path)


def test_invalid_video(invalid_video, metadata_dict, tmp_path):
    with pytest.raises(InvalidMediaError):
        ingest_video(invalid_video, metadata_dict, tmp_path)


def test_video_without_audio(silent_video_no_audio, metadata_dict, tmp_path):
    with pytest.raises(NoAudioStreamError):
        ingest_video(silent_video_no_audio, metadata_dict, tmp_path)


def test_missing_metadata_file(sample_video, tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest_video(sample_video, tmp_path / "missing.json", tmp_path)


def test_invalid_metadata_rejected_before_processing(sample_video, tmp_path):
    with pytest.raises(SchemaError):
        ingest_video(sample_video, {"participant_id": "P"}, tmp_path)
    assert not any(tmp_path.iterdir())
