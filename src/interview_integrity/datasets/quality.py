"""Dataset quality checks: make bad or missing data explicit before it reaches a model.

Severity:
* ``error``: the row (or dataset) should not be used for training/evaluation as-is.
* ``warning``: usable, but a feature group is missing or suspicious; inspect.

Thresholds are deliberately simple and documented so they can be revisited.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .io import load_jsonl
from .schema import DECEPTION_ONLY_DATASETS, AssistanceLabel, DeceptionLabel, InterviewSample, SourceDataset
from .splits import find_group_leakage

MIN_ANSWER_S = 1.0
MAX_ANSWER_S = 15 * 60
SPEECH_RATE_WPM = (60.0, 260.0)  # typical conversational speech is ~120-180 wpm
MAX_ARTICULATION_WPM = 350.0
AI_LABELS = {AssistanceLabel.AI_ASSISTED, AssistanceLabel.AI_VERBATIM, AssistanceLabel.AI_PERSONALIZED}


@dataclass(frozen=True)
class QualityIssue:
    severity: str  # "error" | "warning"
    code: str
    key: str  # recording_id/question_id[/augmentation], or "dataset"
    message: str


def _key(s: InterviewSample) -> str:
    return "/".join(p for p in s.key if p)


def check_sample(s: InterviewSample) -> list[QualityIssue]:
    k, f = _key(s), s.features
    issues: list[QualityIssue] = []

    def add(severity: str, code: str, message: str) -> None:
        issues.append(QualityIssue(severity, code, k, message))

    # audio
    if f.get("audio_is_silent"):
        add("error", "SILENT_AUDIO", "audio track is silent; timing/audio features are not meaningful")
    elif f.get("speech_duration") == 0:
        add("error", "NO_SPEECH_DETECTED", "no speech detected in the answer window")
    if f.get("audio_is_noisy"):
        add("warning", "NOISY_RECORDING", f"low signal-to-noise ratio ({f.get('audio_snr_db')} dB); "
                                         "energy-based timing may be unreliable")
    if f.get("audio_is_clipped"):
        add("warning", "CLIPPED_AUDIO", f"clipping ratio {f.get('audio_clipping_ratio')}")

    # transcript / timing
    if not (s.transcript or "").strip():
        add("warning", "MISSING_TRANSCRIPT", "no transcript; linguistic features are null")
    if s.answer_duration is None:
        add("warning", "MISSING_TIMING", "answer duration unknown (no answer window and no detected speech)")
    elif s.answer_duration <= 0 or s.answer_duration > MAX_ANSWER_S:
        add("error", "INVALID_DURATION", f"answer_duration {s.answer_duration}s outside (0, {MAX_ANSWER_S}]")
    elif s.answer_duration < MIN_ANSWER_S:
        add("warning", "VERY_SHORT_ANSWER", f"answer_duration {s.answer_duration}s < {MIN_ANSWER_S}s")
    if s.response_latency is not None and s.response_latency < 0:
        add("warning", "NEGATIVE_LATENCY", f"answer starts {abs(s.response_latency)}s before the question ends")

    rate = f.get("speech_rate_wpm")
    if rate is not None and not SPEECH_RATE_WPM[0] <= rate <= SPEECH_RATE_WPM[1]:
        add("warning", "EXTREME_SPEECH_RATE", f"speech_rate_wpm {rate} outside {SPEECH_RATE_WPM}")
    art = f.get("articulation_rate_wpm")
    if art is not None and art > MAX_ARTICULATION_WPM:
        add("warning", "EXTREME_ARTICULATION_RATE",
            f"articulation_rate_wpm {art} > {MAX_ARTICULATION_WPM}; speech duration likely underestimated")

    # labels
    if s.source_dataset is SourceDataset.STAGED and s.assistance_label is AssistanceLabel.UNKNOWN:
        add("error", "MISSING_ASSISTANCE_LABEL", "staged sample has no assistance_label")
    if s.source_dataset in DECEPTION_ONLY_DATASETS and s.deception_label is DeceptionLabel.UNKNOWN:
        add("warning", "MISSING_DECEPTION_LABEL", "deception dataset sample has no deception_label")
    if s.assistance_label in AI_LABELS and not s.ai_model_used:
        add("warning", "MISSING_AI_METADATA", f"{s.assistance_label.value} sample has no ai_model_used")
    if s.assistance_label is AssistanceLabel.AI_VERBATIM and not s.generated_ai_answer:
        add("warning", "MISSING_AI_METADATA", "AI_VERBATIM sample has no generated_ai_answer")
    return issues


def check_dataset(samples: Iterable[InterviewSample]) -> list[QualityIssue]:
    samples = list(samples)
    issues = [i for s in samples for i in check_sample(s)]

    for key, n in Counter(s.key for s in samples).items():
        if n > 1:
            issues.append(QualityIssue("error", "DUPLICATE_SAMPLE", "/".join(p for p in key if p),
                                       f"{n} rows share (recording_id, question_id, augmentation)"))

    by_source: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in samples:
        if s.video_sha256:
            by_source[(s.video_sha256, s.question_id)].add(s.recording_id)
    for (sha, qid), recs in by_source.items():
        if len(recs) > 1:
            issues.append(QualityIssue("warning", "DUPLICATE_SOURCE_VIDEO", "dataset",
                                       f"same video file ({sha[:12]}…) and question {qid} under recordings "
                                       f"{sorted(recs)}"))

    for group_key in ("participant_id", "recording_id"):
        for group, splits in find_group_leakage(samples, group_key).items():
            issues.append(QualityIssue("error", "PARTICIPANT_LEAKAGE", "dataset",
                                       f"{group_key} {group} appears in splits {sorted(splits)}"))

    unknown = [s for s in samples if s.participant_id.startswith("unknown:")]
    if unknown and any(s.split for s in samples):
        issues.append(QualityIssue("warning", "UNKNOWN_SPEAKERS", "dataset",
                                   f"{len(unknown)} rows have no real participant ID; splits cannot "
                                   "guarantee the same speaker is not in train and test"))
    return issues


def load_samples(path: str | Path) -> list[InterviewSample]:
    """Load samples from a JSONL file or a directory of per-row JSON files."""
    path = Path(path)
    if path.is_dir():
        return [InterviewSample.from_row(json.loads(p.read_text())) for p in sorted(path.rglob("*.json"))]
    if path.suffix == ".jsonl":
        return load_jsonl(path)
    raise ValueError(f"Unsupported input {path}: use a .jsonl file or a directory of row JSON files")


def summarize(issues: list[QualityIssue], n_samples: int) -> dict:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for i in issues:
        counts[i.severity][i.code] += 1
    return {
        "samples": n_samples,
        "errors": sum(counts["error"].values()),
        "warnings": sum(counts["warning"].values()),
        "by_code": {sev: dict(sorted(c.items())) for sev, c in sorted(counts.items())},
        "issues": [asdict(i) for i in issues],
    }
