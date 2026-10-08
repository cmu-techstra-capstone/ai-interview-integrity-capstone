"""Offline mechanics tests with fake detectors; NOT detector-accuracy evidence."""
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from .conftest import requires_ffmpeg, write_tone_wav
from interview_integrity.modeling.transcript_baseline import (
    MAX_TOKENS, MIN_WORDS, MODEL_LABELS, assess_transcript, evaluate_file,
    validate_inputs, validate_labels, word_count,
)
from interview_integrity.transcription.base import Segment, Transcript

TEXT = " ".join(f"word{i}" for i in range(60))


class Detector:
    def __init__(self, count=100, scores=None):
        self.count = count
        self.scores = scores if scores is not None else {"human_score": 0.75, "ai_text_score": 0.25}
        self.inputs = []

    def token_count(self, text):
        self.inputs.append(("token_count", text))
        return self.count

    def score(self, text):
        self.inputs.append(("score", text))
        return self.scores


def transcript(text=TEXT, language="en"):
    return Transcript([Segment(text)], language=language, provider="synthetic_test")


def test_verified_label_order():
    validate_labels(MODEL_LABELS)
    validate_labels({"0": "Human", "1": "ChatGPT"})
    with pytest.raises(ValueError, match="label mapping"):
        validate_labels({0: "ChatGPT", 1: "Human"})


def test_word_count():
    assert word_count("CUDA Graph doesn't re-launch 3 kernels.") == 6
    assert word_count("你好") == 0


@pytest.mark.parametrize("text,language,flags,status", [
    ("", "en", [], "empty_transcript"),
    ("too short", "en", [], "insufficient_text"),
    (TEXT, "zh", [], "unsupported_or_unknown_language"),
    (TEXT, None, [], "unsupported_or_unknown_language"),
    (TEXT, "en", ["is_clipped"], "audio_quality_review_required"),
])
def test_guards_never_call_detector(text, language, flags, status):
    detector = Detector()
    result = assess_transcript(transcript(text, language), detector=detector, quality_flags=flags)
    assert result["status"] == status and result["ai_text_score"] is None
    assert detector.inputs == []


def test_untagged_sidecar_needs_language_declaration():
    result = assess_transcript(transcript(language=None), detector=Detector(), declared_language="en")
    assert result["status"] == "scored_exploratory"
    result = assess_transcript(transcript(language="zh"), detector=Detector(), declared_language="en")
    assert result["status"] == "unsupported_or_unknown_language"


def test_no_rewriting_no_verdict_no_confidence():
    raw = TEXT + "  um, I-I think.\nLike this."
    detector = Detector(count=MAX_TOKENS)
    result = assess_transcript(transcript(raw), detector=detector)
    assert detector.inputs == [("token_count", raw), ("score", raw)]
    assert result["status"] == "scored_exploratory" and result["ai_text_score"] == 0.25
    assert result["confidence"] is None and result["verdict"] is None
    assert result["text_truncated"] is False and result["llm_cleanup_used"] is False
    assert result["score_type"] == "uncalibrated_softmax"


def test_long_answer_not_silently_truncated():
    detector = Detector(count=MAX_TOKENS + 1)
    result = assess_transcript(transcript(), detector=detector)
    assert result["status"] == "answer_exceeds_model_capacity"
    assert result["ai_text_score"] is None and detector.inputs == [("token_count", TEXT)]


@pytest.mark.parametrize("count", [0, -1, True, 0.1])
def test_bad_token_count(count):
    with pytest.raises(ValueError, match="token count"):
        assess_transcript(transcript(), detector=Detector(count=count))


@pytest.mark.parametrize("scores", [
    {"human_score": math.nan, "ai_text_score": 0.5},
    {"human_score": 0.1, "ai_text_score": math.inf},
    {"human_score": 0.1, "ai_text_score": 0.1},
    {"human_score": -0.1, "ai_text_score": 1.1},
    {"human_score": False, "ai_text_score": 1.0},
    {"human_score": 0.5},
])
def test_bad_scores(scores):
    with pytest.raises(ValueError, match="scores"):
        assess_transcript(transcript(), detector=Detector(scores=scores))


def test_word_guard_boundary():
    assert assess_transcript(transcript("word " * (MIN_WORDS - 1)), detector=Detector())["status"] == "insufficient_text"
    assert assess_transcript(transcript("word " * MIN_WORDS), detector=Detector())["status"] == "scored_exploratory"


def test_sidecar_outputs_no_label_leakage(tmp_path):
    source = tmp_path / "AI_ASSISTED.txt"
    source.write_text(TEXT)
    detector = Detector()
    out = tmp_path / "private"
    result = evaluate_file(source, out, input_kind="transcript", candidate_only=True,
                           detector=detector, declared_language="en")
    assert result["status"] == "scored_exploratory"
    assert result["ground_truth"] is None and result["accuracy_estimated"] is False
    assert result["sends_content_externally"] is False and result["retrained"] is False
    assert detector.inputs[-1] == ("score", TEXT)
    assert (out / "transcript.txt").read_text() == TEXT + "\n"
    assert json.loads((out / "result.json").read_text())["ai_text_score"] == 0.25
    with pytest.raises(ValueError, match="already exists"):
        evaluate_file(source, out, input_kind="transcript", candidate_only=True)


def test_candidate_only_confirmation_required(tmp_path):
    source = tmp_path / "answer.txt"
    source.write_text(TEXT)
    with pytest.raises(ValueError, match="candidate-only"):
        evaluate_file(source, tmp_path / "out", input_kind="transcript", candidate_only=False)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("start,end", [(-1, None), (math.nan, None), (0, math.inf), (1, 1), (2, 1)])
def test_invalid_interval(tmp_path, start, end):
    source = tmp_path / "answer.txt"
    source.write_text(TEXT)
    with pytest.raises(ValueError, match="interval"):
        validate_inputs(source, tmp_path / "out", candidate_only=True, start=start, end=end)


def test_no_timestamp_slicing_sidecars(tmp_path):
    source = tmp_path / "answer.txt"
    source.write_text(TEXT)
    with pytest.raises(ValueError, match="already isolated"):
        evaluate_file(source, tmp_path / "out", input_kind="transcript", candidate_only=True, start=1)


def test_malformed_sidecar_does_not_create_output(tmp_path):
    source = tmp_path / "answer.json"
    source.write_text("invalid json")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        evaluate_file(source, tmp_path / "out", input_kind="transcript", candidate_only=True)
    assert not (tmp_path / "out").exists()


@requires_ffmpeg
def test_real_normalization_asr_to_detector_with_test_doubles(tmp_path):
    source = write_tone_wav(tmp_path / "audio.wav", [(0.5, 1.5), (2.5, 3.5)], 4)
    class Transcriber:
        def transcribe(self, path):
            assert Path(path).name == "normalized.wav"
            return transcript()
    result = evaluate_file(source, tmp_path / "out", input_kind="audio", candidate_only=True,
                           detector=Detector(), transcriber=Transcriber(), start=1, end=3)
    assert result["status"] == "scored_exploratory"
    assert result["audio_interval"] == {"start": 1, "end": 3}
    assert result["transcript_provider"] == "synthetic_test"


@requires_ffmpeg
def test_silence_never_runs_asr_or_detector(tmp_path):
    source = write_tone_wav(tmp_path / "silent.wav", [], 1)
    detector = Detector()
    result = evaluate_file(source, tmp_path / "out", input_kind="audio", candidate_only=True, detector=detector)
    assert result["status"] == "audio_quality_review_required"
    assert result["ai_text_score"] is None and result["asr_details"] is None
    assert "is_silent" in result["quality_flags"] and detector.inputs == []


@requires_ffmpeg
def test_interval_outside_recording(tmp_path):
    source = write_tone_wav(tmp_path / "source.wav", [], 1)
    with pytest.raises(ValueError, match="outside"):
        evaluate_file(source, tmp_path / "out", input_kind="audio", candidate_only=True, end=2)
    assert not (tmp_path / "out").exists()


def test_cli_requires_candidate_confirmation(tmp_path):
    result = subprocess.run([sys.executable, "-m", "interview_integrity.modeling.transcript_baseline", "predict",
                             "--transcript", "answer.txt", "--out-dir", str(tmp_path / "out")],
                            capture_output=True, text=True)
    assert result.returncode == 2 and "--candidate-only" in result.stderr


def test_cli_rejects_public_output(tmp_path):
    result = subprocess.run([sys.executable, "-m", "interview_integrity.modeling.transcript_baseline", "predict",
                             "--transcript", "answer.txt", "--candidate-only", "--out-dir", str(tmp_path / "out")],
                            capture_output=True, text=True)
    assert result.returncode == 2 and "Private output" in result.stderr
