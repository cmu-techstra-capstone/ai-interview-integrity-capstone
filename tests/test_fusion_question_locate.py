from pathlib import Path

import pytest

from interview_integrity.fusion.analyze import analyze_recording
from interview_integrity.fusion.question_locate import load_questions, locate_questions
from interview_integrity.fusion.turns import Word

from .test_fusion_followup import GAZE_EVENT, track

Q = [
    "How would you debug a training job where the loss suddenly becomes NaN?",
    "How would you design a feature store for real-time machine learning predictions?",
    "After a deploy, the p99 latency of a Kubernetes service doubled. How would you investigate?",
]


def speak(text, t, step=0.4):
    out = []
    for w in text.split():
        out.append(Word(w, round(t, 2), round(t + 0.3, 2)))
        t += step
    return out, t


def recording(spoken_questions, answers, gaps):
    words, t = speak("hi okay let me get started with this test", 0.0)
    for q, a, g in zip(spoken_questions, answers, gaps):
        qw, t = speak(q, t + 1.0)
        aw, t = speak(a, t + g)
        words += qw + aw
    return words


ANSWERS = [
    "first I would check the learning rate and look for exploding gradients then I would add gradient clipping and inspect the data batch",
    "I would keep an offline store in the warehouse and an online store in redis and use the same feature code for training and serving",
    "I would compare the old and new versions check CPU throttling and memory then use tracing to find the slow span and roll back first",
]


def test_finds_questions_despite_asr_errors_and_builds_answers():
    spoken = [  # typical recognition errors
        "How would you debug a training job where the loss suddenly becomes NAN?",
        "How would you design a feature store for real time machine learning predictions?",
        "After the deploy the P99 latency of a Kubernetes service doubled how would you investigate?",
    ]
    words = recording(spoken, ANSWERS, gaps=(2.5, 0.6, 0.8))
    turns, located = locate_questions(Q, words)
    assert [q.found for q in located] == [True, True, True]
    assert all(q.match_ratio >= 0.6 for q in located)
    assert [t.speaker for t in turns] == ["interviewer", "interviewee"] * 3
    assert turns[1].text.startswith("first I would check") and turns[1].text.endswith("data batch")
    assert turns[1].start - turns[0].end == pytest.approx(2.5 + 0.1)  # 0.1 = word spacing beyond the 0.3 s word


def test_missing_question_is_reported_not_guessed():
    words = recording([Q[0], Q[2]], [ANSWERS[0], ANSWERS[2]], gaps=(1.0, 1.0))
    turns, located = locate_questions(Q, words)
    assert [q.found for q in located] == [True, False, True]
    assert located[1].start is None
    assert len(turns) == 4  # the answer to Q1 runs until Q3 starts
    assert turns[1].text.endswith("data batch")


def test_questions_must_appear_in_order():
    words = recording([Q[1], Q[0]], [ANSWERS[1], ANSWERS[0]], gaps=(1.0, 1.0))
    _, located = locate_questions(Q[:2], words)
    assert located[0].found and not located[1].found  # Q2 was asked before Q1


def test_end_to_end_with_question_list_flags_delayed_look_away_answer():
    words = recording([q for q in Q] + [Q[0]], ANSWERS + [ANSWERS[0]], gaps=(2.5, 0.6, 0.8, 0.5))
    qs = Q + ["How would you debug a training job where the loss suddenly becomes NaN? Again please"]
    turns, located = locate_questions(qs, words)
    q1_end = located[0].end
    event = {**GAZE_EVENT, "start_s": q1_end + 0.5, "end_s": q1_end + 3.0}
    payload = analyze_recording("SELF", turns, track([event], start=0.0))
    assert payload["answer_windows"] == sum(q.found for q in located)
    assert payload["answers"][0]["followup_pattern"]["conditions"][0]["status"] == "met"  # delayed start


def test_load_questions_formats(tmp_path):
    (tmp_path / "q.txt").write_text("# comment\nWhat is X?\n\nWhy Y?\n")
    assert load_questions(tmp_path / "q.txt") == ["What is X?", "Why Y?"]
    (tmp_path / "q.json").write_text('["A?", "B?"]')
    assert load_questions(tmp_path / "q.json") == ["A?", "B?"]
    (tmp_path / "empty.txt").write_text("# nothing\n")
    with pytest.raises(ValueError):
        load_questions(tmp_path / "empty.txt")
    shipped = Path(__file__).resolve().parents[1] / "experiments/fusion/selftest_questions.txt"
    assert len(load_questions(shipped)) == 6
