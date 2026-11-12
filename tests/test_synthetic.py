import importlib.util
import json
from pathlib import Path

import pytest

from interview_integrity.llm import CachedClient, LLMClient, LLMResponse
from interview_integrity.synthetic import (
    auroc, build_generation_prompt, build_judge_prompt, build_profile, clean_generation, composite,
    grouped_bootstrap_auroc, normalize_for_scoring, participant_of, qa_pairs, question_type, target_words,
    validate_rubric,
)
from interview_integrity.synthetic.rubric import JUDGE_SYSTEM

TRANSCRIPT = (
    "Interviewer: So how are you doing today?|Interviewee: Good thanks.|"
    "Interviewer: So please tell me about yourself.|Interviewee: Im studying chemistry and I run a robotics club "
    "which meets every saturday for middle school kids|Interviewer: mhhmm|Interviewee: and I tutor.|"
    "Interviewer: Tell me one of your weaknesses and what you're doing to overcome it?|"
    "Interviewee: uhm I think I can be a little too detail oriented."
)


def test_question_types_cover_mit_wording():
    assert question_type("given the option to change one thing about yourself what would it be?") == "change_one_thing"
    assert question_type("tell me about a time you were working on a team and faced a challenge. how did you solve that problem?") == "team_challenge"
    assert question_type("do you think you're a leader? tell me why.") == "leadership"
    assert question_type("okay. and why do you think you should get the job?") == "why_hire"
    assert question_type("so please tell me about your background.") == "about_yourself"
    assert question_type("so how are you doing today?") == "smalltalk"
    assert question_type("what's your favourite colour?") == "other"


def test_participant_ids():
    assert participant_of("P12") == ("P12", "pre") and participant_of("pp12") == ("P12", "post")
    with pytest.raises(ValueError):
        participant_of("X1")


def test_qa_pairs_keep_backchannel_inside_answer_and_match_fusion_ids():
    pairs = qa_pairs("P1", TRANSCRIPT)
    assert [(p.question_id, p.question_type) for p in pairs] == [
        ("q01", "smalltalk"), ("q02", "about_yourself"), ("q03", "weakness")]
    assert pairs[1].answer_text.endswith("and I tutor.") and pairs[1].participant_id == "P1"
    assert pairs[2].n_words == 10  # filler "uhm" not counted


def test_profile_never_contains_target_answer():
    pairs = qa_pairs("P1", TRANSCRIPT) + qa_pairs("PP1", TRANSCRIPT.replace("a robotics club", "a debate team"))
    target = pairs[1]  # P1 about_yourself
    prof = build_profile(pairs, target)
    assert "debate team" in prof and "robotics club" not in prof
    assert "robotics club" in build_profile(pairs, pairs[2])


def test_generation_prompts():
    p = qa_pairs("P1", TRANSCRIPT)[2]
    v = build_generation_prompt(p, "AI_VERBATIM")
    assert "weaknesses" in v and "background about me" not in v and "about 40 words" in v
    s = build_generation_prompt(p, "AI_SPOKEN", "I study biology")
    assert "I study biology" in s and "off the top of my head" in s
    with pytest.raises(ValueError):
        build_generation_prompt(p, "AI_PERSONALIZED", "")
    assert target_words(7) == 40 and target_words(137) == 140 and target_words(900) == 250


def test_clean_generation_strips_chat_wrappers():
    raw = 'Sure! Here\'s an answer you can use:\n\n"**One of my weaknesses** is [pause] perfectionism."'
    assert clean_generation(raw) == "One of my weaknesses is perfectionism."


def test_normalisation_removes_format_differences():
    real = "uhm  Im a little too detail-oriented  ah so"
    synth = "Um, I'm a little too detail-oriented. So,"
    assert normalize_for_scoring(real) == normalize_for_scoring(synth) == "im a little too detail oriented so"
    assert "Um" not in build_judge_prompt("Q?", synth)


GOOD = {"specificity": {"score": 4, "evidence": ["a robotics club which meets every saturday"]},
        "genericness": {"score": 2, "evidence": ["I run a robotics club"]},
        "on_topic": {"score": 5, "evidence": []},
        "spoken_style": {"score": 3.0, "evidence": ["and i tutor"]}}


def test_rubric_validation_and_quote_check():
    ans = qa_pairs("P1", TRANSCRIPT)[1].answer_text
    scores, rate, problems = validate_rubric(GOOD, ans)
    assert scores == {"specificity": 4, "genericness": 2, "on_topic": 5, "spoken_style": 3}
    assert rate == 1.0 and problems == []
    assert composite(scores) == 2.0
    bad = {**GOOD, "genericness": {"score": 2, "evidence": ["words that were never said"]},
           "on_topic": {"score": 9}}
    scores, rate, problems = validate_rubric(bad, ans)
    assert scores is None and rate == pytest.approx(2 / 3) and len(problems) == 2
    assert validate_rubric("nope", ans)[0] is None


def test_judge_prompt_never_mentions_ai_detection():
    assert "AI" not in JUDGE_SYSTEM.replace("AI-", "") and "Do not guess who or what produced it" in JUDGE_SYSTEM


def test_auroc_basics_and_ties():
    assert auroc([0, 1], [2, 3]) == 1.0 and auroc([2, 3], [0, 1]) == 0.0
    assert auroc([1, 1], [1, 1]) == 0.5 and auroc([], [1]) is None
    assert auroc([1, 2, 3], [2, 3, 4]) == pytest.approx(7 / 9)  # 1.5 + 2.5 + 3 pairwise wins


def test_grouped_bootstrap_has_interval_around_point():
    items = [(f"g{i % 10}", i % 2, (i % 2) + (i % 7) * 0.1) for i in range(200)]
    r = grouped_bootstrap_auroc(items, n_boot=200)
    assert r["groups"] == 10 and r["ci_low"] <= r["auroc"] <= r["ci_high"]


# ---------------------------------------------------------------- end-to-end with a fake model

class FakeLLM(LLMClient):
    provider = "fake"

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, model, system=None, temperature=0.7, max_tokens=None, **kw):
        self.calls.append(model)
        if system == JUDGE_SYSTEM:
            ans = prompt.split("Answer transcript:\n", 1)[1]
            generic = 5 if "valuable lessons" in ans else 2
            quote = " ".join(ans.split()[:4])
            obj = {d: {"score": s, "evidence": [quote]} for d, s in
                   (("specificity", 6 - generic), ("genericness", generic), ("on_topic", 4), ("spoken_style", 3))}
            return LLMResponse(json.dumps(obj), model, "fake")
        return LLMResponse("Sure! Here is an answer:\n\nI learned valuable lessons about teamwork and "
                           "communication and I always strive to grow and improve myself every day in every "
                           "way that I possibly can as a professional.", model, "fake")


def load_runner():
    path = Path(__file__).resolve().parents[1] / "experiments/synthetic/run_mit_synthetic.py"
    spec = importlib.util.spec_from_file_location("run_mit_synthetic", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_runner_end_to_end_with_fake_model(tmp_path, monkeypatch):
    R = load_runner()
    monkeypatch.setattr(R, "OUT", tmp_path / "out")
    monkeypatch.setattr(R, "REPORTS", tmp_path / "reports")
    fake = FakeLLM()
    monkeypatch.setattr(R, "client", lambda max_calls: CachedClient(fake, tmp_path / "out/cache.jsonl", max_calls))
    long = ("I led the robotics club fundraiser last spring and we raised two thousand dollars by "
            "calling local shops and my roommates helped me organise a raffle night downtown ") * 2
    rows = []
    for pid in range(1, 5):
        for rec in (f"P{pid}", f"PP{pid}"):
            text = "Interviewer: So tell me about yourself.|Interviewee: " + long + \
                   "|Interviewer: Tell me one of your weaknesses and what you're doing to overcome it?|Interviewee: " + long
            rows += [{**p.to_dict(), "eligible": p.n_words >= 40} for p in qa_pairs(rec, text)]
    R.write_jsonl(R.OUT / "answers.jsonl", rows)
    common = ["--participants", "3", "--skip-model-check", "--workers", "2"]
    R.main(["generate", *common, "--generators", "gen/a", "gen/b"])
    syn = R.read_jsonl(R.OUT / "synthetic.jsonl")
    assert len(syn) == 3 * 4 * 3 * 2 and all(r["valid"] and not r["text"].startswith("Sure") for r in syn)
    with pytest.raises(SystemExit):
        R.main(["score", *common, "--generators", "gen/a", "--judge", "gen/a"])
    R.main(["score", *common, "--generators", "gen/a", "gen/b", "--judge", "judge/x"])
    n_before = len(fake.calls)
    R.main(["score", *common, "--generators", "gen/a", "gen/b", "--judge", "judge/x"])
    assert len(fake.calls) == n_before  # second run fully cached
    R.main(["evaluate"])
    report = json.loads(next((tmp_path / "reports").glob("mit-synthetic-content-*.json")).read_text())
    assert report["answers_scored"] == {"real": 12, "synthetic": 72}
    assert report["auroc_all_synthetic"]["genericness"]["auroc"] == 1.0
    assert report["ai_assistance_probability"] is None
    assert "robotics club fundraiser" not in json.dumps(report)  # aggregate only, no interview text
