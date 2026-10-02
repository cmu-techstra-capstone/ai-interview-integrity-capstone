import json

import pytest

from interview_integrity.cli import main
from interview_integrity.datasets.io import write_jsonl
from interview_integrity.datasets.quality import check_dataset, check_sample
from interview_integrity.datasets.schema import InterviewSample


def _s(**kw):
    base = dict(interview_id="I1", participant_id="P1", question_id="Q1", source_dataset="staged",
                assistance_label="HUMAN_UNASSISTED", transcript="An answer.", answer_start=1.0, answer_end=21.0,
                answer_duration=20.0, features={"speech_duration": 15.0, "speech_rate_wpm": 140.0})
    features = {**base.pop("features"), **kw.pop("features", {})}
    return InterviewSample(**{**base, **kw}, features=features).validate()


def codes(issues):
    return sorted(i.code for i in issues)


def test_clean_sample_has_no_issues():
    assert check_sample(_s()) == []


@pytest.mark.parametrize("kw,code,severity", [
    (dict(transcript=None), "MISSING_TRANSCRIPT", "warning"),
    (dict(answer_start=None, answer_end=None, answer_duration=None), "MISSING_TIMING", "warning"),
    (dict(answer_end=None, answer_duration=2000.0), "INVALID_DURATION", "error"),
    (dict(answer_end=None, answer_duration=0.4), "VERY_SHORT_ANSWER", "warning"),
    (dict(features={"speech_rate_wpm": 400.0}), "EXTREME_SPEECH_RATE", "warning"),
    (dict(features={"articulation_rate_wpm": 700.0}), "EXTREME_ARTICULATION_RATE", "warning"),
    (dict(features={"audio_is_silent": True}), "SILENT_AUDIO", "error"),
    (dict(features={"speech_duration": 0}), "NO_SPEECH_DETECTED", "error"),
    (dict(features={"audio_is_noisy": True, "audio_snr_db": 4.0}), "NOISY_RECORDING", "warning"),
    (dict(features={"audio_is_clipped": True}), "CLIPPED_AUDIO", "warning"),
    (dict(assistance_label="UNKNOWN"), "MISSING_ASSISTANCE_LABEL", "error"),
    (dict(assistance_label="AI_ASSISTED"), "MISSING_AI_METADATA", "warning"),
    (dict(response_latency=-0.5), "NEGATIVE_LATENCY", "warning"),
])
def test_sample_checks(kw, code, severity):
    issues = check_sample(_s(**kw))
    assert code in codes(issues)
    assert next(i for i in issues if i.code == code).severity == severity


def test_ai_metadata_not_required_for_human_answers():
    assert "MISSING_AI_METADATA" not in codes(check_sample(_s(assistance_label="HUMAN_UNASSISTED")))


def test_ai_verbatim_with_metadata_is_clean():
    s = _s(assistance_label="AI_VERBATIM", ai_model_used="m", generated_ai_answer="text")
    assert check_sample(s) == []


def test_deception_dataset_missing_label():
    s = _s(source_dataset="real_life_deception", assistance_label="UNKNOWN", deception_label="UNKNOWN")
    assert codes(check_sample(s)) == ["MISSING_DECEPTION_LABEL"]


def test_dataset_duplicates_and_leakage():
    a = _s(split="train", video_sha256="ab" * 32)
    b = _s(split="test", video_sha256="ab" * 32)  # same key, leaked participant
    c = _s(interview_id="I2", recording_id="I2", video_sha256="ab" * 32, split="train")  # same file, new id
    found = codes(check_dataset([a, b, c]))
    assert "DUPLICATE_SAMPLE" in found
    assert "PARTICIPANT_LEAKAGE" in found
    assert "DUPLICATE_SOURCE_VIDEO" in found


def test_unknown_speakers_warning_only_when_split():
    s = _s(participant_id="unknown:clip1", source_dataset="real_life_deception", assistance_label="UNKNOWN",
           deception_label="TRUTHFUL")
    assert "UNKNOWN_SPEAKERS" not in codes(check_dataset([s]))
    s.split = "train"
    assert "UNKNOWN_SPEAKERS" in codes(check_dataset([s]))


def test_quality_cli(tmp_path, capsys):
    good, bad = tmp_path / "good.jsonl", tmp_path / "bad.jsonl"
    write_jsonl([_s()], good)
    write_jsonl([_s(features={"audio_is_silent": True})], bad)
    assert main(["quality", "--input", str(good)]) == 0
    assert main(["quality", "--input", str(bad), "--report", str(tmp_path / "r.json")]) == 1
    assert json.loads((tmp_path / "r.json").read_text())["by_code"]["error"]["SILENT_AUDIO"] == 1
    # a directory of per-row JSON files also works
    d = tmp_path / "rows"
    d.mkdir()
    (d / "a.json").write_text(json.dumps(_s().to_row()))
    assert main(["quality", "--input", str(d)]) == 0
