import json

import pytest

from interview_integrity.fusion.followup import evaluate_interview
from interview_integrity.fusion.llm_brief import (
    SYSTEM_PROMPT, build_messages, generate_brief, validate_brief,
)
from interview_integrity.llm.base import LLMClient, LLMResponse

from .test_fusion_followup import GAZE_EVENT, interview, track


def suggested():
    r = evaluate_interview("P1", interview(), track([GAZE_EVENT]))[0]
    assert r.status == "suggest_followup"
    return r


GOOD = {
    "summary": "The answer began 2.5 s after the question, with a sustained gaze change from 101.0 to 104.0 s, followed by a fluent answer.",
    "observations": [{"text": "Gaze moved away from the candidate's own baseline.", "timestamps": [[101.0, 104.0]]}],
    "alternative_explanations": ["Thinking before answering", "Looking at notes or a resume"],
    "suggested_followup_questions": ["What was the hardest technical decision on that robot, and why?"],
    "limitations": ["The rule is unvalidated."],
}


class FakeClient(LLMClient):
    provider = "fake"

    def __init__(self, text):
        self.text, self.calls = text, []

    def generate(self, prompt, *, model, system=None, temperature=0.7, max_tokens=None):
        self.calls.append((system, prompt))
        return LLMResponse(self.text, model, self.provider)


def test_messages_exclude_answer_text_unless_approved():
    r = suggested()
    system, user = build_messages(r, answer_text="SECRET ANSWER")
    assert "SECRET ANSWER" not in user and system == SYSTEM_PROMPT
    payload = json.loads(user)
    assert payload["rule_status"] == "suggest_followup" and len(payload["conditions"]) == 5
    _, user2 = build_messages(r, answer_text="SECRET ANSWER", include_answer_text=True)
    assert "SECRET ANSWER" in user2


def test_only_suggested_answers_get_a_brief():
    r = evaluate_interview("P1", interview(), track([]))[0]
    with pytest.raises(ValueError):
        build_messages(r)


def test_good_brief_passes():
    assert validate_brief(GOOD, suggested()) == []


@pytest.mark.parametrize("text", [
    "The candidate was probably cheating.",
    "There is an 80% chance of AI use.",
    "This looks AI-generated.",
    "High likelihood the candidate used AI.",
])
def test_verdicts_and_probabilities_are_rejected(text):
    bad = {**GOOD, "summary": text}
    assert any("banned wording" in v for v in validate_brief(bad, suggested()))


def test_invented_timestamps_and_missing_alternatives_are_rejected():
    bad = {**GOOD, "observations": [{"text": "x", "timestamps": [[55.0, 57.0]]}], "alternative_explanations": []}
    v = validate_brief(bad, suggested())
    assert any("timestamp not in input" in x for x in v)
    assert any("alternative_explanations" in x for x in v)


def test_generate_brief_accepts_valid_and_flags_invalid_output():
    ok = generate_brief(FakeClient("```json\n" + json.dumps(GOOD) + "\n```"), suggested(), model="m")
    assert ok["accepted"] and ok["violations"] == []
    bad = generate_brief(FakeClient("not json"), suggested(), model="m")
    assert not bad["accepted"]
