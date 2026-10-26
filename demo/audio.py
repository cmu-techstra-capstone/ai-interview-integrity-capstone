"""Audio analysis for the demo: speech/pause timing from a recording, using the repo's VAD + timing code.

Accepts 16-bit PCM WAV directly. Other formats (mp3, m4a, mp4, webm) need `ffmpeg` on PATH.
Transcription is OPTIONAL and only happens if `faster-whisper` happens to be installed; otherwise paste
the transcript text instead. Timing thresholds are uncalibrated demo heuristics (weak evidence).
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from scoring import PRIOR, clamp, timing_raw, timing_signals, to_scale, zone_for  # also sets sys.path

from interview_integrity.audio.vad import detect_speech_intervals, frame_levels  # noqa: E402
from interview_integrity.features.timing import compute_timing_features  # noqa: E402

ENVELOPE_POINTS = 240
WINDOW_S, HOP_S = 10.0, 5.0


def ensure_wav(src: Path, workdir: Path) -> Path:
    """Return a 16-bit PCM WAV path (converting with ffmpeg when needed)."""
    try:
        with wave.open(str(src), "rb") as wf:
            if wf.getsampwidth() == 2:
                return src
    except (wave.Error, EOFError):
        pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("This file is not a 16-bit PCM WAV and ffmpeg is not installed. Upload a .wav file.")
    out = workdir / "converted.wav"
    proc = subprocess.run(
        [ffmpeg, "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(out)],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError("ffmpeg could not read this file: " + proc.stderr.strip().splitlines()[-1][:200])
    return out


def try_transcribe(wav: Path) -> dict[str, Any] | None:
    """Optional local Whisper transcription (only if faster-whisper is installed)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return None
    from interview_integrity.transcription.base import Word

    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(wav), word_timestamps=True, vad_filter=False)
    words, texts = [], []
    for seg in segments:
        texts.append(seg.text.strip())
        for w in seg.words or []:
            words.append(Word(text=w.word.strip(), start=float(w.start), end=float(w.end)))
    return {"text": " ".join(texts).strip(), "words": words}


def _envelope(levels) -> list[float]:
    db = levels.db
    if not db:
        return []
    bucket = max(1, len(db) // ENVELOPE_POINTS)
    out = []
    for i in range(0, len(db), bucket):
        peak = max(db[i:i + bucket])
        out.append(round(clamp((peak + 70.0) / 65.0), 3))
    return out


def analyze(wav: Path, *, question_end: float | None = None, word_count: int | None = None, words=None) -> dict[str, Any]:
    levels = frame_levels(wav)
    duration = round(levels.duration, 2)
    intervals = detect_speech_intervals(wav)
    result: dict[str, Any] = {
        "duration": duration, "envelope": _envelope(levels), "speech": [list(i) for i in intervals],
        "pauses": [], "windows": [], "features": {}, "signals": [], "timing_score": None, "warnings": [],
    }
    if not intervals:
        result["warnings"].append("No speech detected (silent, or too little dynamic range).")
        return result

    start, end = intervals[0][0], intervals[-1][1]
    feats = compute_timing_features(
        speech_intervals=intervals, answer_start=start, answer_end=end,
        question_end=question_end, word_count=word_count, words=words,
    )
    result["features"] = feats
    result["pauses"] = [[round(a[1], 2), round(b[0], 2)] for a, b in zip(intervals, intervals[1:]) if b[0] - a[1] >= 0.4]
    sigs = timing_signals(feats, word_count)
    result["signals"] = sigs
    raw = timing_raw(sigs)
    if raw is not None:
        score = to_scale(PRIOR + 0.8 * (raw - PRIOR))
        result["timing_score"] = score
        result["timing_zone"] = zone_for(score)[0]
    if end - start < 8:
        result["warnings"].append("Short clip: timing signals are very weak below ~10 seconds of speech.")

    t = 0.0
    while t + 6.0 <= duration:
        w0, w1 = t, min(t + WINDOW_S, duration)
        inside = [iv for iv in intervals if iv[1] > w0 and iv[0] < w1]
        if inside:
            wf = compute_timing_features(speech_intervals=inside, answer_start=w0, answer_end=w1)
            wraw = timing_raw([s for s in timing_signals(wf) if s["name"] in ("uniform_cadence", "few_pauses")])
            if wraw is not None:
                result["windows"].append(
                    {"t0": round(w0, 1), "t1": round(w1, 1), "score": to_scale(PRIOR + 0.8 * (wraw - PRIOR))}
                )
        t += HOP_S
    return result
