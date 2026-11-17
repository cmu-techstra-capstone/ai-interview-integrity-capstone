from interview_integrity.fusion.turns import (
    Word, align_turns, build_answer_windows, parse_turker_transcript, tokenize,
)

TRANSCRIPT = (
    "Interviewer: So how are you doing?|Interviewee: Im pretty good.|"
    "Interviewer: Ok well so please tell me about yourself.|"
    "Interviewee: ok uhm so I study chemistry at a state college|Interviewer: mhhmm|"
    "Interviewee: and I like robots a lot.|"
    "Interviewer: Tell me about a time you demonstrated leadership.|"
    "Interviewee: I organised a bake sale."
)


def words_from(spec):
    """spec: list of (text, start) with 0.3 s words."""
    return [Word(t, s, s + 0.3) for t, s in spec]


def asr_words():
    seq = [
        ("so", 0.0), ("how", 0.3), ("are", 0.6), ("you", 0.9), ("doing", 1.2),
        ("I'm", 2.0), ("pretty", 2.3), ("good.", 2.6),
        ("OK", 3.5), ("well", 3.8), ("so", 4.1), ("please", 4.4), ("tell", 4.7), ("me", 5.0),
        ("about", 5.3), ("yourself.", 5.6),
        # 3.1 s gap before the answer
        ("OK", 9.0), ("so", 9.3), ("I", 9.6), ("study", 9.9), ("chemistry", 10.2), ("at", 10.5),
        ("a", 10.8), ("state", 11.1), ("college", 11.4),
        ("and", 12.5), ("I", 12.8), ("like", 13.1), ("robots", 13.4), ("a", 13.7), ("lot.", 14.0),
        ("Tell", 15.0), ("me", 15.3), ("about", 15.6), ("a", 15.9), ("time", 16.2), ("you", 16.5),
        ("demonstrated", 16.8), ("leadership.", 17.1),
        ("I", 18.0), ("organised", 18.3), ("a", 18.6), ("bake", 18.9), ("sale.", 19.2),
    ]
    return words_from(seq)


def test_tokenize_drops_apostrophes_and_punctuation():
    assert tokenize("I'm pretty-good, MIT!") == ["im", "pretty", "good", "mit"]


def test_parse_merges_same_speaker_and_keeps_order():
    turns = parse_turker_transcript("Interviewer: a b|Interviewer: c|Interviewee: d|stray text")
    assert [(t.speaker, t.text) for t in turns] == [("interviewer", "a b c"), ("interviewee", "d stray text")]


def test_alignment_gives_turn_times_and_backchannel_stays_in_answer():
    turns = align_turns(parse_turker_transcript(TRANSCRIPT), asr_words())
    windows = build_answer_windows(turns)
    # "how are you doing" (4 content tokens) counts as a question, "mhhmm" does not.
    assert [w.question_id for w in windows] == ["q01", "q02", "q03"]
    w = windows[1]
    assert w.timing_ok, w.timing_note
    assert abs(w.question_end - 5.9) < 1e-6
    assert abs(w.answer_start - 9.0) < 1e-6
    assert abs(w.latency - 3.1) < 1e-6
    assert "robots" in w.answer_text and w.answer_end == 14.3


def test_missing_question_end_makes_timing_unreliable():
    words = [w for w in asr_words() if w.start not in (5.0, 5.3, 5.6)]  # drop "me about yourself"
    windows = build_answer_windows(align_turns(parse_turker_transcript(TRANSCRIPT), words))
    assert not windows[1].timing_ok
    assert "question end" in windows[1].timing_note


def test_no_asr_words_means_no_timing():
    windows = build_answer_windows(align_turns(parse_turker_transcript(TRANSCRIPT), []))
    assert windows and all(not w.timing_ok and w.latency is None for w in windows)
