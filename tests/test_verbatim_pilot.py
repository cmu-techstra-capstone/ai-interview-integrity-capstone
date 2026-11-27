"""Pilot mechanics tests with synthetic transcripts; no quality/accuracy claim."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from interview_integrity.modeling.beemo_benchmark import text_hash, write_json
from interview_integrity.modeling.transcript_baseline import sha256
from interview_integrity.modeling.verbatim_pilot import (
    ASR_SETTINGS, assess, load_manifest, prepare, score, validate_samples,
)
from interview_integrity.transcription.base import Segment, Transcript

TEXT = "word " * 60


class Detector:
    def __init__(self, count=100, value=-1.5):
        self.count, self.value, self.inputs = count, value, []

    def token_count(self, text):
        self.inputs.append(("tokens", text))
        return self.count

    def score(self, text):
        self.inputs.append(("score", text))
        return {"score": self.value, "checkpoint_loading_verified": True}


def text_inputs(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text(TEXT)
    inputs = tmp_path / "inputs.json"
    write_json(inputs, {"purpose": "verbatim_asr_pilot", "candidate_only": True, "samples": [
        {"id": "known_ai", "input_kind": "text", "path": "source.txt", "language": "en",
         "condition": "ai_text_control", "provenance_status": "known_generated"}]})
    return inputs


def frozen(tmp_path):
    inputs = text_inputs(tmp_path)
    prepare(inputs, tmp_path / "prepared", tmp_path)
    return tmp_path / "prepared/manifest.json"


def test_text_controls_never_fill_audio_conditions(tmp_path):
    path = frozen(tmp_path)
    d = Detector()
    result = score(path, tmp_path / "out", tmp_path, "cpu", factory=lambda c, v: d)
    assert result["missing_primary_audio_conditions"] == ["ai_verbatim", "human_self_script", "human_spontaneous"]
    assert result["primary_audio_condition_counts"] == {}
    assert result["rows"][0]["score"] == -1.5
    assert result["confidence"] is result["verdict"] is None
    assert result["accuracy_estimated"] is result["threshold_selected"] is result["training"] is False
    assert result["integrity_status"] == "verified"
    assert d.inputs == [("tokens", TEXT.strip()), ("score", TEXT.strip())]
    assert "Unknown reading source remains unknown" not in (tmp_path / "out/report.md").read_text()


@pytest.mark.parametrize("condition,provenance", [
    ("human_self_script", "known_generated"), ("ai_verbatim", "unknown"),
    ("unknown", "protocol_verified"), ("ai_text_control", "self_reported"),
])
def test_provenance_cannot_be_guessed_or_ai_text_used_as_human(tmp_path, condition, provenance):
    inputs = text_inputs(tmp_path)
    data = json.loads(inputs.read_text())
    data["samples"][0].update(condition=condition, provenance_status=provenance)
    with pytest.raises(ValueError):
        validate_samples(data, tmp_path)


@pytest.mark.parametrize("data", [[], {}, {"purpose": "verbatim_asr_pilot", "candidate_only": False, "samples": []}])
def test_invalid_pilot_metadata(data, tmp_path):
    with pytest.raises(ValueError):
        validate_samples(data, tmp_path)


@pytest.mark.parametrize("kind", ["source", "transcript", "condition", "metadata", "asr"])
def test_frozen_integrity_checks(tmp_path, kind):
    path = frozen(tmp_path)
    manifest = json.loads(path.read_text())
    if kind == "source":
        (tmp_path / "source.txt").write_text(TEXT + "changed")
    elif kind == "transcript":
        Path(manifest["samples"][0]["transcript_path"]).write_text("{}")
    elif kind == "condition":
        manifest["samples"][0]["condition"] = "human_self_script"
        write_json(path, manifest)
    elif kind == "metadata":
        p = Path(manifest["inputs_file"])
        p.write_text(p.read_text() + " ")
    else:
        manifest["asr_settings"] = {**ASR_SETTINGS, "initial_prompt": "AI answer"}
        write_json(path, manifest)
    with pytest.raises(ValueError):
        load_manifest(path)


@pytest.mark.parametrize("text,language,flags,status", [
    ("", "en", [], "empty_transcript"), ("tiny", "en", [], "insufficient_text"),
    (TEXT, "zh", [], "unsupported_or_unknown_language"),
    (TEXT, "en", ["is_clipped"], "audio_quality_review_required"),
])
def test_quality_language_and_length_abstention(text, language, flags, status):
    d = Detector()
    result = assess(Transcript([Segment(text)], language=language), d, flags)
    assert result["status"] == status and result["score"] is None
    assert not d.inputs


def test_long_text_no_truncation():
    d = Detector(count=513)
    r = assess(Transcript([Segment(TEXT)], language="en"), d, [])
    assert r["status"] == "answer_exceeds_capacity" and r["score"] is None
    assert d.inputs == [("tokens", TEXT.strip())]


@pytest.mark.parametrize("value", [float("inf"), float("nan"), True, "-2"])
def test_invalid_signed_statistics(value):
    with pytest.raises(ValueError, match="signed"):
        assess(Transcript([Segment(TEXT)], language="en"), Detector(value=value), [])


def test_inference_error_persisted_and_run_fails(tmp_path):
    path = frozen(tmp_path)
    with pytest.raises(RuntimeError, match="Inference errors"):
        score(path, tmp_path / "out", tmp_path, "cpu", factory=lambda c, d: Detector(value=float("nan")))
    r = json.loads((tmp_path / "out/results.json").read_text())
    assert r["rows"][0]["status"] == "inference_error" and r["rows"][0]["score"] is None


def test_unchanged_sources_checked_after_scoring(tmp_path):
    path = frozen(tmp_path)
    class Changed(Detector):
        def score(self, text):
            (tmp_path / "source.txt").write_text(TEXT + "mutated")
            return super().score(text)
    with pytest.raises(ValueError, match="identity"):
        score(path, tmp_path / "out", tmp_path, "cpu", factory=lambda c, d: Changed())
    assert not (tmp_path / "out/report.md").exists()


def test_optional_imports_lazy():
    p = subprocess.run([sys.executable, "-c", "from interview_integrity.modeling import verbatim_pilot; import sys; assert not {'torch','transformers','faster_whisper','ctranslate2'} & set(sys.modules)"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_cli_refuses_public_output_before_loading(tmp_path):
    p = subprocess.run([sys.executable, "-m", "interview_integrity.modeling.verbatim_pilot", "score", "--manifest", "missing",
                        "--out-dir", str(tmp_path / "out")], capture_output=True, text=True)
    assert p.returncode == 2 and "Private outputs" in p.stderr


def test_unknown_and_personalized_audio_not_human_negatives(tmp_path):
    # Synthetic frozen audio fixtures: no ASR or real speaker data needed.
    inputs = text_inputs(tmp_path)
    data = json.loads(inputs.read_text())
    data["samples"] = [{**data["samples"][0], "id": name, "input_kind": "audio", "condition": name,
                         "provenance_status": "unknown" if name == "unknown" else "self_reported"}
                       for name in ["unknown", "ai_personalized"]]
    write_json(inputs, data)
    rows = validate_samples(data, tmp_path)
    for row in rows:
        trans = tmp_path / (row["id"] + ".json")
        transcript = Transcript([Segment(TEXT)], language="en")
        write_json(trans, transcript.to_dict())
        row.update(transcript_path=str(trans), transcript_file_sha256=sha256(trans),
                   text_sha256=text_hash(transcript.text), word_count=60, language_detected="en", quality_flags=[])
    path = tmp_path / "manifest.json"
    write_json(path, {"purpose": "verbatim_asr_pilot", "candidate_only": True, "integrity_status": "verified",
                     "inputs_file": str(inputs), "inputs_sha256": sha256(inputs), "asr_settings": ASR_SETTINGS, "samples": rows})
    r = score(path, tmp_path / "out", tmp_path, "cpu", factory=lambda c, d: Detector())
    assert r["primary_audio_condition_counts"] == {}
    assert len(r["missing_primary_audio_conditions"]) == 3
