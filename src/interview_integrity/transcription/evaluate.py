"""Provider-independent evaluation of speech-to-text output against reference transcripts.

Used to compare STT candidates on *our* data before choosing one. Metrics:

* WER: (substitutions + deletions + insertions) / reference words, after lowercasing
  and stripping punctuation.
* Filler recall: share of reference filled pauses ("um", "uh", ...) that also appear
  in the hypothesis (bag-of-words count, per clip). Matters because filler features
  are only meaningful if the STT keeps disfluencies.
* Word-timestamp coverage: share of hypothesis transcripts with word-level timestamps.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from ..features.linguistic import FILLED_PAUSES, tokenize
from .base import Transcript
from .sidecar import SidecarTranscriber


@dataclass(frozen=True)
class TranscriptScore:
    clip_id: str
    reference_words: int
    substitutions: int
    deletions: int
    insertions: int
    reference_fillers: int
    hypothesis_fillers: int
    has_word_timestamps: bool

    @property
    def wer(self) -> float | None:
        if not self.reference_words:
            return None
        return (self.substitutions + self.deletions + self.insertions) / self.reference_words

    @property
    def filler_recall(self) -> float | None:
        if not self.reference_fillers:
            return None
        return min(self.hypothesis_fillers, self.reference_fillers) / self.reference_fillers


def edit_counts(ref: list[str], hyp: list[str]) -> tuple[int, int, int]:
    """Levenshtein alignment counts: (substitutions, deletions, insertions)."""
    # dp[j] = (cost, subs, dels, ins) for ref[:i] vs hyp[:j]
    prev = [(j, 0, 0, j) for j in range(len(hyp) + 1)]
    for i in range(1, len(ref) + 1):
        cur = [(i, 0, i, 0)]
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                cur.append(prev[j - 1])
                continue
            sub, dele, ins = prev[j - 1], prev[j], cur[j - 1]
            best = min(
                (sub[0] + 1, sub[1] + 1, sub[2], sub[3]),
                (dele[0] + 1, dele[1], dele[2] + 1, dele[3]),
                (ins[0] + 1, ins[1], ins[2], ins[3] + 1),
            )
            cur.append(best)
        prev = cur
    _, s, d, n = prev[-1]
    return s, d, n


def score_transcript(clip_id: str, reference: Transcript, hypothesis: Transcript) -> TranscriptScore:
    ref, hyp = tokenize(reference.text), tokenize(hypothesis.text)
    s, d, n = edit_counts(ref, hyp)
    return TranscriptScore(
        clip_id=clip_id,
        reference_words=len(ref),
        substitutions=s,
        deletions=d,
        insertions=n,
        reference_fillers=sum(t in FILLED_PAUSES for t in ref),
        hypothesis_fillers=sum(t in FILLED_PAUSES for t in hyp),
        has_word_timestamps=hypothesis.has_word_timestamps,
    )


def summarize_scores(scores: Iterable[TranscriptScore]) -> dict:
    scores = list(scores)
    ref_words = sum(s.reference_words for s in scores)
    errors = sum(s.substitutions + s.deletions + s.insertions for s in scores)
    ref_fill = sum(s.reference_fillers for s in scores)
    hyp_fill_matched = sum(min(s.hypothesis_fillers, s.reference_fillers) for s in scores)
    return {
        "clips": len(scores),
        "reference_words": ref_words,
        "corpus_wer": round(errors / ref_words, 4) if ref_words else None,
        "reference_fillers": ref_fill,
        "filler_recall": round(hyp_fill_matched / ref_fill, 4) if ref_fill else None,
        "word_timestamp_coverage": round(sum(s.has_word_timestamps for s in scores) / len(scores), 4)
        if scores else None,
        "per_clip": [{**asdict(s), "wer": s.wer, "filler_recall": s.filler_recall} for s in scores],
    }


def evaluate_directories(reference_dir: str | Path, hypothesis_dir: str | Path) -> dict:
    """Pair ``<clip_id>.txt|.json`` files by stem and score them."""
    def index(d: Path) -> dict[str, Path]:
        files = [p for p in Path(d).iterdir() if p.suffix in (".txt", ".json")]
        return {p.stem.removesuffix(".transcript"): p for p in files}

    refs, hyps = index(Path(reference_dir)), index(Path(hypothesis_dir))
    common = sorted(set(refs) & set(hyps))
    if not common:
        raise ValueError("No clips with matching file stems in both directories")
    scores = [
        score_transcript(c, SidecarTranscriber(refs[c]).transcribe(), SidecarTranscriber(hyps[c]).transcribe())
        for c in common
    ]
    report = summarize_scores(scores)
    report["missing_hypotheses"] = sorted(set(refs) - set(hyps))
    return report
