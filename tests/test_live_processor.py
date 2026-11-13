"""Unit tests for live STT windowing / dedupe (fake STT only)."""

from __future__ import annotations

import struct

from interview_integrity.live.fake_stt import FakeLiveTranscriber
from interview_integrity.live.pcm import PcmChunk
from interview_integrity.live.processor import LiveProcessor, _dedupe_token_suffix
from interview_integrity.live.session import LiveSession


def _tone_chunk(seconds: float = 1.0, rate: int = 16000) -> PcmChunk:
    frames = int(seconds * rate)
    samples = []
    for i in range(frames):
        v = 2500 if (i // 40) % 2 == 0 else -2500
        samples.append(struct.pack("<h", v))
    raw = b"".join(samples)
    return PcmChunk(sample_rate=rate, channels=1, samples=raw, duration_ms=seconds * 1000)


def test_dedupe_token_suffix():
    assert _dedupe_token_suffix([], ["a", "b"]) == ["a", "b"]
    assert _dedupe_token_suffix(["a", "b", "c"], ["b", "c", "d"]) == ["d"]
    assert _dedupe_token_suffix(["a", "b"], ["x", "y"]) == ["x", "y"]


def test_processor_produces_transcript_with_fake_stt():
    session = LiveSession.create(consent_confirmed=True, stt_name="fake-live")
    processor = LiveProcessor(transcriber_factory=lambda _n: FakeLiveTranscriber())

    for seq in range(1, 6):
        session.accept_chunk(
            sequence=seq,
            chunk=_tone_chunk(1.0),
            max_session_bytes=5_000_000,
            client_rel_start_ms=(seq - 1) * 1000,
        )
        payload = processor.process_after_chunk(session)
        assert payload["session_id"] == session.session_id

    final = processor.process_after_chunk(session, force=True)
    assert final["detection"]["status"] == "model_unavailable"
    assert any(seg["text"] for seg in final["transcript_segments"])
    # Second forced pass should not explode; dedupe should avoid runaway duplicates.
    again = processor.process_after_chunk(session, force=True)
    texts = [s["text"] for s in again["transcript_segments"]]
    assert len(texts) >= 1
