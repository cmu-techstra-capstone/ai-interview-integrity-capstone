import pytest

from interview_integrity.features.linguistic import extract_linguistic_features
from interview_integrity.features.timing import compute_timing_features, speech_intervals_from_words
from interview_integrity.transcription import SidecarTranscriber


def test_linguistic_basic_counts():
    f = extract_linguistic_features("Um, I think I think testing matters. You know, it catches bugs early.")
    assert f["word_count"] == 13
    assert f["sentence_count"] == 2
    assert f["avg_sentence_length"] == pytest.approx(6.5)
    assert f["filler_word_count"] == 2  # "um", "you know"
    assert f["repetition_count"] == 1  # "I think I think"
    assert f["self_correction_count"] == 1
    assert 0 < f["type_token_ratio"] <= 1


def test_linguistic_repairs_and_word_repeats():
    f = extract_linguistic_features("The the result was, sorry, the outcome was good.")
    assert f["repetition_count"] == 1
    assert f["self_correction_count"] == 2


def test_linguistic_empty_text():
    f = extract_linguistic_features("")
    assert f["word_count"] == 0
    assert f["sentence_count"] is None
    assert f["type_token_ratio"] is None
    assert f["filler_rate_per_100_words"] is None


def test_linguistic_unpunctuated_text_has_no_sentence_count():
    f = extract_linguistic_features("i think testing matters because it catches bugs")
    assert f["word_count"] == 8
    assert f["sentence_count"] is None
    assert f["avg_sentence_length"] is None


def test_qa_overlap_and_similarity_placeholder():
    f = extract_linguistic_features("Testing matters a lot.", question_text="Why does testing matter?")
    assert f["qa_content_word_overlap"] == pytest.approx(0.5)  # {"testing", "matter"} vs answer tokens
    assert f["qa_semantic_similarity"] is None

    class FakeScorer:
        name = "fake"

        def score(self, question, answer):
            return 0.42

    f = extract_linguistic_features("Testing.", question_text="Why?", similarity_scorer=FakeScorer())
    assert f["qa_semantic_similarity"] == pytest.approx(0.42)


def test_speech_intervals_from_words(transcript_path):
    words = SidecarTranscriber(transcript_path).transcribe().words
    assert speech_intervals_from_words(words, merge_gap=0.3) == [(0.5, 1.5), (2.5, 3.5)]


def test_timing_features_known_values():
    f = compute_timing_features(
        speech_intervals=[(0.5, 1.5), (2.5, 3.5)],
        answer_start=0.5, answer_end=3.5, question_end=0.2, word_count=13,
    )
    assert f["answer_duration"] == pytest.approx(3.0)
    assert f["speech_duration"] == pytest.approx(2.0)
    assert f["pause_count"] == 1
    assert f["mean_pause_duration"] == pytest.approx(1.0)
    assert f["speech_rate_wpm"] == pytest.approx(260.0)
    assert f["articulation_rate_wpm"] == pytest.approx(390.0)
    assert f["response_latency"] == pytest.approx(0.3)


def test_timing_latency_null_without_question_end():
    f = compute_timing_features(speech_intervals=[(0, 1)], answer_start=0.0, answer_end=1.0, word_count=2)
    assert f["response_latency"] is None


def test_timing_all_null_without_answer_window():
    f = compute_timing_features(speech_intervals=[], answer_start=None, answer_end=None)
    assert f["answer_duration"] is None
    assert f["speech_duration"] is None
    assert f["pause_count"] is None


def test_timing_short_gaps_are_not_pauses():
    f = compute_timing_features(
        speech_intervals=[(0.0, 1.0), (1.1, 2.0)], answer_start=0.0, answer_end=2.0, min_pause=0.3
    )
    assert f["pause_count"] == 0
    assert f["mean_pause_duration"] is None
