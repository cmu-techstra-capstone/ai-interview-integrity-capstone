"""Localhost FastAPI security and offline-analysis endpoint tests (no model downloads)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from interview_integrity.api.app import create_app
from interview_integrity.api.config import ApiConfigError, ApiSettings
from interview_integrity.api.paths import PathValidationError, resolve_authorized_file

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from .conftest import FIXTURES, requires_ffmpeg


@pytest.fixture
def recordings_root(tmp_path, sample_video, transcript_path) -> Path:
    root = tmp_path / "authorized"
    pilot = root / "pilot"
    pilot.mkdir(parents=True)
    video = pilot / "sample.mp4"
    shutil.copy(sample_video, video)
    meta = {
        "interview_id": "INT001",
        "participant_id": "P001",
        "source_dataset": "staged",
        "question_id": "Q01",
        "question_text": "Why does software testing matter?",
        "assistance_label": "HUMAN_UNASSISTED",
    }
    (pilot / "sample.metadata.json").write_text(json.dumps(meta))
    shutil.copy(transcript_path, pilot / "sample.transcript.json")
    return root


@pytest.fixture
def api_settings(recordings_root, tmp_path) -> ApiSettings:
    return ApiSettings(
        host="127.0.0.1",
        port=8765,
        recordings_dir=recordings_root,
        interim_dir=tmp_path / "interim",
        out_dir=tmp_path / "out",
        allowed_origins=("chrome-extension://test-extension-id", "http://127.0.0.1:8765"),
        relax_host_check=True,
    )


@pytest.fixture
def client(api_settings) -> TestClient:
    app = create_app(api_settings)
    return TestClient(app)


def test_api_settings_rejects_non_loopback_host():
    with pytest.raises(ApiConfigError):
        ApiSettings(host="0.0.0.0", recordings_dir=Path("."))


def test_api_settings_rejects_wildcard_cors():
    with pytest.raises(ApiConfigError):
        ApiSettings.from_env(
            {
                "INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS": "*",
            }
        )


def test_health_endpoint(client, api_settings):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["detection_model"] == "unavailable"
    assert body["recordings_dir_configured"] is True
    assert body["allowed_origins_configured"] is True
    assert "recordings_dir" not in body  # no filesystem path leakage


@requires_ffmpeg
def test_valid_offline_analysis(client):
    res = client.post(
        "/v1/analyze-offline",
        json={
            "recording_relpath": "pilot/sample.mp4",
            "metadata_relpath": "pilot/sample.metadata.json",
            "transcript_relpath": "pilot/sample.transcript.json",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    analysis = body["analysis"]
    assert analysis["schema_version"] == "analysis.v1"
    assert analysis["source"] == "offline_processing"
    assert analysis["is_synthetic"] is False
    assert analysis["detection"]["status"] == "model_unavailable"
    assert analysis["detection"]["raw_score"] is None
    assert analysis["detection"]["confidence_value"] is None
    assert analysis["answers"]
    # Client-facing provenance must not expose absolute server paths.
    assert "/" not in analysis["provenance"].get("video_path", "") or analysis["provenance"]["video_path"] == "sample.mp4"
    assert analysis["provenance"]["video_path"] == "sample.mp4"


def test_invalid_request_schema(client):
    res = client.post("/v1/analyze-offline", json={"recording_relpath": "x"})
    assert res.status_code == 422  # pydantic validation


def test_missing_recording(client):
    res = client.post(
        "/v1/analyze-offline",
        json={
            "recording_relpath": "pilot/missing.mp4",
            "metadata_relpath": "pilot/sample.metadata.json",
        },
    )
    assert res.status_code == 404
    err = res.json()["error"]
    assert err["code"] == "file_not_found"
    assert "/Users" not in err["message"]
    assert "tmp" not in err["message"].lower() or "authorized" in err["message"].lower()


def test_path_traversal_rejected(client):
    res = client.post(
        "/v1/analyze-offline",
        json={
            "recording_relpath": "../etc/passwd",
            "metadata_relpath": "pilot/sample.metadata.json",
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_path"


def test_absolute_path_rejected(client):
    res = client.post(
        "/v1/analyze-offline",
        json={
            "recording_relpath": "/etc/passwd",
            "metadata_relpath": "pilot/sample.metadata.json",
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_path"


def test_symlink_escape_rejected(api_settings, tmp_path):
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"not-a-real-video")
    link = api_settings.recordings_dir / "escape.mp4"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not available")
    with pytest.raises(PathValidationError) as exc:
        resolve_authorized_file(
            api_settings,
            "escape.mp4",
            field="recording_relpath",
            allowed_suffixes=api_settings.allowed_video_suffixes,
        )
    assert exc.value.code == "path_outside_root"


def test_outside_directory_access(client):
    res = client.post(
        "/v1/analyze-offline",
        json={
            "recording_relpath": "pilot/../../outside.mp4",
            "metadata_relpath": "pilot/sample.metadata.json",
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_path"


def test_unsupported_file_type(client, recordings_root):
    bad = recordings_root / "pilot" / "notes.txt"
    bad.write_text("hello")
    res = client.post(
        "/v1/analyze-offline",
        json={
            "recording_relpath": "pilot/notes.txt",
            "metadata_relpath": "pilot/sample.metadata.json",
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "unsupported_file"


def test_sidecar_path_validation(client):
    res = client.post(
        "/v1/analyze-offline",
        json={
            "recording_relpath": "pilot/sample.mp4",
            "metadata_relpath": "pilot/sample.metadata.json",
            "transcript_relpath": "../secrets.txt",
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_path"


@requires_ffmpeg
def test_forbidden_origin(client):
    res = client.post(
        "/v1/analyze-offline",
        headers={"Origin": "https://evil.example"},
        json={
            "recording_relpath": "pilot/sample.mp4",
            "metadata_relpath": "pilot/sample.metadata.json",
            "transcript_relpath": "pilot/sample.transcript.json",
        },
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forbidden_origin"


@requires_ffmpeg
def test_allowed_extension_origin(client):
    res = client.post(
        "/v1/analyze-offline",
        headers={"Origin": "chrome-extension://test-extension-id"},
        json={
            "recording_relpath": "pilot/sample.mp4",
            "metadata_relpath": "pilot/sample.metadata.json",
            "transcript_relpath": "pilot/sample.transcript.json",
        },
    )
    assert res.status_code == 200


def test_loopback_host_middleware_blocks_foreign_host(recordings_root, tmp_path):
    settings = ApiSettings(
        host="127.0.0.1",
        recordings_dir=recordings_root,
        interim_dir=tmp_path / "i",
        out_dir=tmp_path / "o",
        allowed_origins=(),
        relax_host_check=False,
    )
    app = create_app(settings)
    c = TestClient(app)
    # Starlette TestClient sets Host to testserver by default.
    res = c.get("/health")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forbidden_host"


def test_loopback_host_allows_127(recordings_root, tmp_path):
    settings = ApiSettings(
        host="127.0.0.1",
        recordings_dir=recordings_root,
        interim_dir=tmp_path / "i",
        out_dir=tmp_path / "o",
        allowed_origins=(),
        relax_host_check=False,
    )
    app = create_app(settings)
    c = TestClient(app)
    res = c.get("/health", headers={"Host": "127.0.0.1:8765"})
    assert res.status_code == 200


@requires_ffmpeg
def test_error_responses_do_not_leak_transcript_text(client):
    # Force a missing metadata path — ensure body never echoes transcript contents.
    res = client.post(
        "/v1/analyze-offline",
        json={
            "recording_relpath": "pilot/sample.mp4",
            "metadata_relpath": "pilot/does-not-exist.json",
            "transcript_relpath": "pilot/sample.transcript.json",
        },
    )
    assert res.status_code == 404
    text = res.text
    transcript = (FIXTURES / "sample_transcript.json").read_text()
    assert "Um, I think" not in text
    assert "testing matters" not in text
    assert transcript[:40] not in text


@requires_ffmpeg
def test_api_to_extension_mapper_compatibility(client):
    """Integration: FastAPI analysis.v1 payload is consumable by the TS contract shape."""
    res = client.post(
        "/v1/analyze-offline",
        json={
            "recording_relpath": "pilot/sample.mp4",
            "metadata_relpath": "pilot/sample.metadata.json",
            "transcript_relpath": "pilot/sample.transcript.json",
        },
    )
    analysis = res.json()["analysis"]
    # Minimal shape checks mirroring mapAnalysisContract expectations.
    assert analysis["schema_version"] == "analysis.v1"
    assert analysis["detection"]["confidence_status"] == "unavailable_not_calibrated"
    assert analysis["detection"]["confidence_value"] is None
    answer = analysis["answers"][0]
    assert answer["question_id"]
    assert isinstance(answer["transcript_segments"], list)
    assert isinstance(answer["evidence_signals"], list)
