import json

import pytest

from interview_integrity.cli import main
from interview_integrity.transcription.base import Transcript
from interview_integrity.transcription.evaluate import edit_counts, score_transcript, summarize_scores


def T(text, words=False):
    if words:
        toks = text.split()
        return Transcript.from_dict({"segments": [{"text": text, "start": 0, "end": len(toks),
                                                   "words": [{"word": w, "start": i, "end": i + 0.5}
                                                             for i, w in enumerate(toks)]}]})
    return Transcript.from_dict({"text": text})


@pytest.mark.parametrize("ref,hyp,expected", [
    ("a b c", "a b c", (0, 0, 0)),
    ("a b c", "a x c", (1, 0, 0)),
    ("a b c", "a c", (0, 1, 0)),
    ("a b c", "a b c d", (0, 0, 1)),
    ("", "a", (0, 0, 1)),
])
def test_edit_counts(ref, hyp, expected):
    assert edit_counts(ref.split(), hyp.split()) == expected


def test_score_ignores_case_and_punctuation_and_counts_fillers():
    s = score_transcript("c1", T("Um, I think, uh, it works."), T("i think it works", words=True))
    assert s.reference_words == 6 and s.deletions == 2 and s.wer == pytest.approx(2 / 6)
    assert s.reference_fillers == 2 and s.filler_recall == 0.0
    assert s.has_word_timestamps


def test_summary_is_corpus_level():
    a = score_transcript("a", T("one two three four"), T("one two three four"))
    b = score_transcript("b", T("um yes"), T("um no"))
    r = summarize_scores([a, b])
    assert r["corpus_wer"] == pytest.approx(1 / 6, abs=1e-4)  # reported to 4 decimals
    assert r["filler_recall"] == 1.0
    assert r["word_timestamp_coverage"] == 0.0


def test_stt_eval_cli(tmp_path, capsys):
    ref, hyp = tmp_path / "ref", tmp_path / "hyp"
    ref.mkdir(); hyp.mkdir()
    (ref / "clip1.txt").write_text("Um, I was at home.")
    (ref / "clip2.txt").write_text("No sir.")
    (hyp / "clip1.json").write_text(json.dumps({"text": "I was at home"}))
    assert main(["stt-eval", "--reference", str(ref), "--hypothesis", str(hyp),
                 "--report", str(tmp_path / "r.json")]) == 0
    r = json.loads((tmp_path / "r.json").read_text())
    assert r["clips"] == 1 and r["missing_hypotheses"] == ["clip2"]
    assert r["filler_recall"] == 0.0
