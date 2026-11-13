"""Localhost live session / chunk API tests (fake STT; no model downloads)."""

from __future__ import annotations

import base64
import struct
from pathlib import Path

import pytest

from interview_integrity.api.app import create_app
from interview_integrity.api.config import ApiSettings
from interview_integrity.live.fake_stt import FakeLiveTranscriber
from interview_integrity.live.processor import LiveProcessor

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


def _pcm_silence(frames: int = 16000) -> str:
    raw = b"\x00\x00" * frames
    return base64.b64encode(raw).decode("ascii")


def _pcm_tone(frames: int = 16000, amp: int = 2000) -> str:
    samples = []
    for i in range(frames):
        # crude square-ish pattern so VAD/fake STT have non-empty audio
        v = amp if (i // 80) % 2 == 0 else -amp
        samples.append(struct.pack("<h", v))
    return base64.b64encode(b"".join(samples)).decode("ascii")


@pytest.fixture
def api_settings(tmp_path) -> ApiSettings:
    return ApiSettings(
        host="127.0.0.1",
        port=8765,
        recordings_dir=tmp_path / "authorized",
        interim_dir=tmp_path / "interim",
        out_dir=tmp_path / "out",
        allowed_origins=("chrome-extension://test-extension-id",),
        relax_host_check=True,
        live_default_stt="fake-live",
        live_max_sessions=2,
        live_max_chunk_bytes=256 * 1024,
        live_max_session_bytes=2 * 1024 * 1024,
    )


@pytest.fixture
def client(api_settings) -> TestClient:
    app = create_app(api_settings)
    # Force fake STT regardless of factory defaults.
    app.state.live_processor = LiveProcessor(
        transcriber_factory=lambda _name: FakeLiveTranscriber(),
    )
    return TestClient(app)


def test_health_reports_live_fields(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["live_audio_enabled"] is True
    assert body["live_sessions_active"] == 0
    assert body["detection_model"] == "unavailable"


def test_live_start_requires_consent_and_meet_flag(client):
    res = client.post("/v1/live/sessions", json={"consent_confirmed": False, "meet_tab_confirmed": True})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "consent_required"

    res = client.post("/v1/live/sessions", json={"consent_confirmed": True, "meet_tab_confirmed": False})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "meet_tab_required"


def test_live_chunk_happy_path_fake_stt(client):
    start = client.post(
        "/v1/live/sessions",
        json={"consent_confirmed": True, "meet_tab_confirmed": True, "stt": "fake-live"},
    )
    assert start.status_code == 200
    session_id = start.json()["live"]["session_id"]

    # Send ~5 seconds of audio as 1s chunks so inference threshold is met.
    for seq in range(1, 6):
        res = client.post(
            f"/v1/live/sessions/{session_id}/chunks",
            json={
                "sequence": seq,
                "sample_rate": 16000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "pcm_base64": _pcm_tone(16000),
                "duration_ms": 1000,
                "client_rel_start_ms": (seq - 1) * 1000,
            },
        )
        assert res.status_code == 200, res.text
        live = res.json()["live"]
        assert live["session_id"] == session_id

    stop = client.post(f"/v1/live/sessions/{session_id}/stop")
    assert stop.status_code == 200
    live = stop.json()["live"]
    assert live["status"] == "stopped"
    assert live["detection"]["status"] == "model_unavailable"
    assert live["audio_research"]["status"] in {"model_unavailable", "insufficient_evidence"}
    assert live["transcript_research"]["status"] in {"model_unavailable", "insufficient_evidence"}
    # Fake STT should have produced at least one finalized segment after enough audio.
    assert any(seg.get("text") for seg in live.get("transcript_segments") or [])


def test_rejects_duplicate_and_out_of_order_sequences(client):
    start = client.post(
        "/v1/live/sessions",
        json={"consent_confirmed": True, "meet_tab_confirmed": True, "stt": "fake-live"},
    )
    session_id = start.json()["live"]["session_id"]
    payload = {
        "sequence": 1,
        "sample_rate": 16000,
        "channels": 1,
        "encoding": "pcm_s16le",
        "pcm_base64": _pcm_silence(8000),
        "duration_ms": 500,
    }
    assert client.post(f"/v1/live/sessions/{session_id}/chunks", json=payload).status_code == 200
    dup = client.post(f"/v1/live/sessions/{session_id}/chunks", json=payload)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "duplicate_sequence"

    bad = dict(payload, sequence=3, pcm_base64=_pcm_silence(8000))
    ooo = client.post(f"/v1/live/sessions/{session_id}/chunks", json=bad)
    assert ooo.status_code == 409
    assert ooo.json()["error"]["code"] == "unexpected_sequence"


def test_rejects_oversized_and_bad_format(client):
    start = client.post(
        "/v1/live/sessions",
        json={"consent_confirmed": True, "meet_tab_confirmed": True, "stt": "fake-live"},
    )
    session_id = start.json()["live"]["session_id"]
    huge = base64.b64encode(b"\x00" * (300 * 1024)).decode("ascii")
    res = client.post(
        f"/v1/live/sessions/{session_id}/chunks",
        json={
            "sequence": 1,
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "pcm_s16le",
            "pcm_base64": huge,
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_audio"

    res = client.post(
        f"/v1/live/sessions/{session_id}/chunks",
        json={
            "sequence": 1,
            "sample_rate": 16000,
            "channels": 2,
            "encoding": "pcm_s16le",
            "pcm_base64": _pcm_silence(100),
        },
    )
    assert res.status_code == 400


def test_origin_guard_still_applies_to_live(api_settings):
    app = create_app(api_settings)
    app.state.live_processor = LiveProcessor(transcriber_factory=lambda _n: FakeLiveTranscriber())
    client = TestClient(app)
    res = client.post(
        "/v1/live/sessions",
        json={"consent_confirmed": True, "meet_tab_confirmed": True},
        headers={"Origin": "https://evil.example"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forbidden_origin"


def test_stop_unknown_session(client):
    res = client.post("/v1/live/sessions/does-not-exist/stop")
    assert res.status_code == 404


def test_no_audio_files_persisted_after_stop(client, tmp_path):
    start = client.post(
        "/v1/live/sessions",
        json={"consent_confirmed": True, "meet_tab_confirmed": True, "stt": "fake-live"},
    )
    session_id = start.json()["live"]["session_id"]
    client.post(
        f"/v1/live/sessions/{session_id}/chunks",
        json={
            "sequence": 1,
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "pcm_s16le",
            "pcm_base64": _pcm_tone(16000),
            "duration_ms": 1000,
        },
    )
    client.post(f"/v1/live/sessions/{session_id}/stop")
    # No wav/pcm artifacts under tmp paths from this test process.
    leftovers = list(Path(tmp_path).rglob("*.wav")) + list(Path(tmp_path).rglob("*.pcm"))
    assert leftovers == []
