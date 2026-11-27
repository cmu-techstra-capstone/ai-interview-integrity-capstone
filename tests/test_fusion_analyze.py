import importlib.util
import json
from pathlib import Path

import pytest

from interview_integrity.fusion.analyze import analyze_recording, answer_windows
from interview_integrity.fusion.transcript_input import (
    TranscriptError, load_transcript, needs_asr, turns_from_segments,
)
from interview_integrity.fusion.turns import TimedTurn, Turn, Word
from interview_integrity.llm import LLMClient, LLMResponse

from .test_fusion_followup import GAZE_EVENT, track
from .test_fusion_llm_brief import GOOD

FLUENT = "I led a team of five students to build a robot for the regional contest and we won second place overall"
HALTING = "uh I um think that uh it was um a project where uh I sort of um did some uh work on the um design part"


def words(text, start, step=0.4, pause_every=None):
    out, t = [], start
    for i, w in enumerate(text.split()):
        out.append({"text": w, "start": round(t, 3), "end": round(t + 0.3, 3)})
        t += step + (1.5 if pause_every and i % pause_every == pause_every - 1 else 0)
    return out


def seg(speaker, text, start, pause_every=None):
    ws = words(text, start, pause_every=pause_every)
    return {"speaker": speaker, "text": text, "start_seconds": ws[0]["start"], "end_seconds": ws[-1]["end"], "words": ws}


def timed_segments():
    """Four questions; q01's answer starts 2.5 s after the question (overlaps GAZE_EVENT at 101-104 s)."""
    s = []
    for q_start, a_start, text, pe in ((97.0, 102.5, FLUENT, None), (147.0, 150.4, HALTING, 3),
                                       (197.0, 200.5, HALTING, 4), (247.0, 250.3, FLUENT, None)):
        q = seg("Aditi", "Tell me about a project you led.", q_start)
        q["end_seconds"] = a_start - (2.5 if q_start == 97.0 else 0.4)
        q["words"][-1]["end"] = q["end_seconds"]
        s += [q, seg("Leo", text, a_start, pe)]
    return s


def test_text_and_json_formats(tmp_path):
    (tmp_path / "t.txt").write_text("Interviewer: Tell me about yourself please.|Interviewee: I study chemistry.")
    assert [t.speaker for t in load_transcript(tmp_path / "t.txt")] == ["interviewer", "interviewee"]
    (tmp_path / "a.json").write_text(json.dumps({"answers": [{"transcript_segments": [
        {"speaker": "Interviewer", "text": "Why this job?", "start_seconds": 1, "end_seconds": 2},
        {"speaker": "Candidate", "text": "Because", "start_seconds": 3, "end_seconds": 4},
        {"speaker": "candidate", "text": "I like it.", "start_seconds": 4, "end_seconds": 5}]}]}))
    turns = load_transcript(tmp_path / "a.json")
    assert all(isinstance(t, TimedTurn) for t in turns) and len(turns) == 2
    assert turns[1].text == "Because I like it." and turns[1].end == 5
    (tmp_path / "bad.txt").write_text("no speakers here")
    with pytest.raises(TranscriptError):
        load_transcript(tmp_path / "bad.txt")


def test_display_names_need_interviewer_mapping():
    segs = [{"speaker": "Aditi", "text": "Why?"}, {"speaker": "Leo", "text": "Because."}]
    with pytest.raises(TranscriptError, match="interviewer_names"):
        turns_from_segments(segs)
    turns = turns_from_segments(segs, ["aditi"])
    assert [t.speaker for t in turns] == ["interviewer", "interviewee"] and isinstance(turns[0], Turn)


def test_needs_asr_only_without_candidate_word_times():
    assert needs_asr([Turn("interviewer", "q")])
    timed = turns_from_segments(timed_segments(), ["aditi"])
    assert not needs_asr(timed)
    no_words = [TimedTurn(t.speaker, t.text, t.start, t.end, 1.0, True, True, ()) for t in timed]
    assert needs_asr(no_words)


def test_timed_transcript_end_to_end_without_asr():
    turns = turns_from_segments(timed_segments(), ["aditi"])
    payload = analyze_recording("REC1", turns, track([GAZE_EVENT]))
    assert payload["timing_source"] == "transcript_timestamps" and payload["answer_windows"] == 4
    first = payload["answers"][0]["followup_pattern"]
    assert first["status"] == "suggest_followup", first["conditions"]
    assert payload["status_counts"]["suggest_followup"] == 1
    assert payload["ai_assistance_probability"] is None and payload["visual"]["events"][0]["start_s"] == 101.0
    assert "question_text" not in payload["answers"][0]
    json.dumps(payload)


def test_untimed_transcript_uses_asr_alignment():
    timed = turns_from_segments(timed_segments(), ["aditi"])
    plain = [Turn(t.speaker, t.text) for t in timed]
    asr = [Word(w.text, w.start, w.end) for t in timed for w in t.words]
    windows, source = answer_windows(plain, asr)
    assert source == "asr_alignment" and len(windows) == 4 and windows[0].timing_ok
    with pytest.raises(ValueError):
        answer_windows(plain, None)


class FakeLLM(LLMClient):
    provider = "fake"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, *, model, system=None, temperature=0.7, max_tokens=None, **kw):
        self.calls += 1
        return LLMResponse(json.dumps(GOOD), model, "fake")


def test_briefs_only_for_flagged_answers_and_no_visual_means_insufficient():
    turns = turns_from_segments(timed_segments(), ["aditi"])
    fake = FakeLLM()
    payload = analyze_recording("REC1", turns, track([GAZE_EVENT]), brief_client=fake, brief_model="m")
    assert fake.calls == 1 and payload["reviewer_briefs"] == {"requested": 1, "accepted": 1, "model": "m"}
    assert payload["answers"][0]["followup_pattern"]["reviewer_brief"] == GOOD
    no_video = analyze_recording("REC1", turns, None)
    assert no_video["visual"] == {"available": False, "events": []}
    assert "suggest_followup" not in no_video["status_counts"]


def test_cli_without_video(tmp_path):
    path = Path(__file__).resolve().parents[1] / "experiments/fusion/analyze_video.py"
    spec = importlib.util.spec_from_file_location("analyze_video", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    video = tmp_path / "interview.mp4"
    video.write_bytes(b"not really a video")
    (tmp_path / "t.json").write_text(json.dumps(timed_segments()))
    out = tmp_path / "out.json"
    mod.main([str(video), "--transcript", str(tmp_path / "t.json"), "--interviewer-name", "Aditi",
              "--no-video", "--out", str(out), "--work-dir", str(tmp_path / "work"), "--include-text"])
    payload = json.loads(out.read_text())
    assert payload["recording_id"] == "interview" and payload["source"]["transcript"] == "t.json"
    assert payload["answers"][0]["question_text"] == "Tell me about a project you led."
    assert payload["answers"][0]["followup_pattern"]["status"] == "insufficient_evidence"
