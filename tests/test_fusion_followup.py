import json

from interview_integrity.fusion.followup import (
    INSUFFICIENT, MET, NO_PATTERN, NOT_MET, SUGGEST, UNMEASURABLE,
    FollowupConfig, VisualTrack, evaluate_interview, evaluate_window, self_baseline,
)
from interview_integrity.fusion.turns import AnswerWindow, Word

FLUENT = "I led a team of five students to build a robot for the regional contest and we won second place overall"
HALTING = "uh I um think that uh it was um a project where uh I sort of um did some uh work on the um design part"


def answer_words(start, n=20, step=0.4, pause_every=None):
    out, t = [], start
    for i in range(n):
        out.append(Word(f"w{i}", t, t + 0.3))
        t += step + (1.5 if pause_every and i % pause_every == pause_every - 1 else 0)
    return tuple(out)


def window(qid, q_end, a_start, text=FLUENT, pause_every=None, timing_ok=True):
    words = answer_words(a_start, pause_every=pause_every)
    return AnswerWindow(qid, "Tell me about a project.", q_end, a_start, words[-1].end, text, words,
                        timing_ok=timing_ok, timing_note="" if timing_ok else "answer start not reliably aligned")


def track(events, start=30.0, end=400.0, fps=2.0, measured=True):
    frames, t = [], start
    while t <= end:
        frames.append({"timestamp_s": t, "head_deviation": False if measured else None,
                       "eye_deviation": None})
        t += 1 / fps
    return VisualTrack(tuple(frames), tuple(events), 30.0, True, True)


GAZE_EVENT = {"type": "relative_gaze_change", "start_s": 101.0, "end_s": 104.0, "duration_s": 3.0}


def interview():
    # q01 is the target; others are halting / paused so q01 is at or below the personal median.
    return [
        window("q01", 100.0, 102.5),
        window("q02", 150.0, 150.4, HALTING, pause_every=3),
        window("q03", 200.0, 200.5, HALTING, pause_every=4),
        window("q04", 250.0, 250.3, FLUENT),
    ]


def test_all_three_conditions_suggest_followup_and_never_give_probability():
    res = evaluate_interview("P1", interview(), track([GAZE_EVENT]))
    r = res[0]
    assert r.status == SUGGEST
    assert [r.condition(n).status for n in ("delayed_start", "look_away", "fluent_answer")] == [MET, MET, MET]
    assert r.condition("look_away").timestamps == ((101.0, 104.0),)
    assert r.ai_assistance_probability is None
    d = r.to_dict()
    assert "question_text" not in d and d["ai_assistance_probability"] is None
    json.dumps(d)  # serialisable


def test_immediate_answer_is_no_pattern_even_with_look_away():
    ws = interview()
    res = evaluate_interview("P1", ws, track([{**GAZE_EVENT, "start_s": 150.0, "end_s": 153.0}]))
    assert res[3].condition("delayed_start").status == NOT_MET
    assert res[1].status == NO_PATTERN


def test_no_visual_event_is_no_pattern():
    r = evaluate_interview("P1", interview(), track([]))[0]
    assert r.condition("look_away").status == NOT_MET and r.status == NO_PATTERN


def test_halting_answer_is_not_fluent():
    r = evaluate_interview("P1", interview(), track([]))[1]
    assert r.condition("fluent_answer").status == NOT_MET


def test_missing_visual_measurements_abstain():
    r = evaluate_interview("P1", interview(), track([GAZE_EVENT], measured=False))[0]
    assert r.condition("look_away").status == UNMEASURABLE
    assert r.status == INSUFFICIENT


def test_window_inside_calibration_period_abstains():
    w = window("q01", 10.0, 12.5)
    base = self_baseline(interview(), FollowupConfig())
    r = evaluate_window("P1", w, track([GAZE_EVENT]), base)
    assert r.condition("look_away").status == UNMEASURABLE
    assert "baseline period" in r.condition("look_away").explanation


def test_unreliable_timing_abstains_on_latency():
    w = window("q01", 100.0, 102.5, timing_ok=False)
    r = evaluate_window("P1", w, track([GAZE_EVENT]), (0.0, 0.0))
    assert r.condition("delayed_start").status == UNMEASURABLE
    assert r.status == INSUFFICIENT


def test_too_few_answers_for_personal_baseline_abstains_on_fluency():
    r = evaluate_interview("P1", interview()[:2], track([GAZE_EVENT]))[0]
    assert r.condition("fluent_answer").status == UNMEASURABLE


def test_optional_scores_are_context_only():
    base = self_baseline(interview(), FollowupConfig())
    r = evaluate_window("P1", interview()[0], track([GAZE_EVENT]), base, read_like_score=0.1, ai_text_score=None)
    assert r.status == SUGGEST  # optional scores never change the status
    assert r.condition("read_like_delivery").status == NOT_MET
    assert r.condition("ai_like_text").status == UNMEASURABLE
    assert not r.condition("read_like_delivery").required


def test_evidence_signals_follow_contract_shape():
    r = evaluate_interview("P1", interview(), track([GAZE_EVENT]))[0]
    sigs = r.evidence_signals()
    assert {s["signal_name"] for s in sigs} >= {"fusion_delayed_start", "fusion_look_away", "fusion_fluent_answer"}
    for s in sigs:
        assert s["confidence"] is None and s["sample_key"] == "P1/q01"
        assert s["modality"] in {"audio", "visual", "transcript"}
        for word in ("cheat", "ai-generated", "dishonest"):
            assert word not in s["explanation"].lower()
