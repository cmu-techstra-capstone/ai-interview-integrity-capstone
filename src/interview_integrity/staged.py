"""Tooling for staged (controlled) interviews: templates, protocol validation, label import.

Lets the team prepare pilot recordings without code edits:

    interview-integrity staged template ...      -> metadata JSON skeleton per recording
    interview-integrity staged import-labels ... -> fill question/answer timestamps from a label file
    interview-integrity staged validate ...      -> protocol checks before processing

Label files are tab-separated ``start<TAB>end<TAB>label`` (seconds), the format exported
by Audacity label tracks and easy to write by hand. Labels look like ``Q01 question``
and ``Q01 answer`` (``-`` or ``_`` also accepted as separators).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .datasets.schema import AssistanceLabel, RecordingMetadata, SchemaError, SourceDataset

PARTICIPANT_ID_RE = re.compile(r"^P\d{3}$")  # P001
INTERVIEW_ID_RE = re.compile(r"^STG-P\d{3}-S\d{2}$")  # STG-P001-S01 (participant + session)
QUESTION_ID_RE = re.compile(r"^Q\d{2}$")  # Q01
AI_LABELS = {AssistanceLabel.AI_ASSISTED, AssistanceLabel.AI_VERBATIM, AssistanceLabel.AI_PERSONALIZED}
_LABEL_RE = re.compile(r"^\s*(?P<qid>[A-Za-z0-9]+)[\s_-]+(?P<kind>question|answer)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ProtocolIssue:
    severity: str  # "error" | "warning"
    code: str
    message: str


def load_question_bank(path: str | Path) -> list[dict[str, str]]:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list) or not all(isinstance(q, dict) and q.get("question_id") for q in data):
        raise SchemaError("Question bank must be a JSON list of objects with 'question_id' (and 'question_text')")
    return data


def make_template(
    interview_id: str,
    participant_id: str,
    questions: list[dict[str, str]],
    conditions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Metadata skeleton for one staged recording. Timestamps and AI fields start as null."""
    conditions = conditions or {}
    entries = []
    for q in questions:
        qid = q["question_id"]
        label = conditions.get(qid)
        entries.append({
            "question_id": qid,
            "question_text": q.get("question_text"),
            "assistance_label": label,
            "question_start": None,
            "question_end": None,
            "answer_start": None,
            "answer_end": None,
            "ai_model_used": None,
            "ai_prompt_used": None,
            "generated_ai_answer": None,
            "response_notes": None,
        })
    return {
        "interview_id": interview_id,
        "participant_id": participant_id,
        "source_dataset": SourceDataset.STAGED.value,
        "questions": entries,
    }


def parse_condition_args(values: list[str] | None) -> dict[str, str]:
    """Parse ``Q01=HUMAN_UNASSISTED`` style assignments (labels validated later)."""
    out = {}
    for v in values or []:
        if "=" not in v:
            raise SchemaError(f"Condition must look like Q01=AI_VERBATIM, got {v!r}")
        qid, label = v.split("=", 1)
        out[qid.strip()] = label.strip().upper()
    return out


def read_labels(path: str | Path) -> dict[str, dict[str, tuple[float, float]]]:
    """Parse a label file into ``{question_id: {"question": (s, e), "answer": (s, e)}}``."""
    spans: dict[str, dict[str, tuple[float, float]]] = {}
    seen: set[tuple[str, str]] = set()
    for lineno, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith(("#", "\\")):  # Audacity frequency lines start with "\"
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise SchemaError(f"{path}:{lineno}: expected 'start<TAB>end<TAB>label'")
        try:
            start, end = float(parts[0]), float(parts[1])
        except ValueError:
            raise SchemaError(f"{path}:{lineno}: start/end must be numbers") from None
        m = _LABEL_RE.match(parts[2])
        if not m:
            raise SchemaError(f"{path}:{lineno}: label {parts[2]!r} must look like 'Q01 question' or 'Q01 answer'")
        if end < start:
            raise SchemaError(f"{path}:{lineno}: end ({end}) before start ({start})")
        qid, kind = m["qid"], m["kind"].lower()
        if (qid.lower(), kind) in seen:
            raise SchemaError(f"{path}:{lineno}: duplicate '{qid} {kind}' label")
        seen.add((qid.lower(), kind))
        spans.setdefault(qid, {})[kind] = (round(start, 3), round(end, 3))
    return spans


def apply_labels(metadata: dict[str, Any], spans: dict[str, dict[str, tuple[float, float]]]) -> dict[str, Any]:
    """Return a copy of ``metadata`` with question/answer timestamps filled from ``spans``."""
    questions = {q["question_id"]: dict(q) for q in metadata.get("questions", [])}
    by_lower = {qid.lower(): qid for qid in questions}  # hand-typed labels: match case-insensitively
    unknown = sorted(qid for qid in spans if qid.lower() not in by_lower)
    if unknown:
        raise SchemaError(f"Labels refer to question_ids not in the metadata: {unknown}")
    for qid, kinds in spans.items():
        q = questions[by_lower[qid.lower()]]
        if "question" in kinds:
            q["question_start"], q["question_end"] = kinds["question"]
        if "answer" in kinds:
            q["answer_start"], q["answer_end"] = kinds["answer"]
    return {**metadata, "questions": [questions[q["question_id"]] for q in metadata["questions"]]}


def validate_staged(metadata: dict[str, Any]) -> list[ProtocolIssue]:
    """Protocol checks for a staged recording. Schema violations are reported as errors."""
    issues: list[ProtocolIssue] = []

    def add(severity: str, code: str, message: str) -> None:
        issues.append(ProtocolIssue(severity, code, message))

    for q in metadata.get("questions", []):
        if not q.get("assistance_label"):
            add("error", "MISSING_ASSISTANCE_LABEL", f"{q.get('question_id')}: staged answers need an assistance_label")
    try:
        meta = RecordingMetadata.from_dict(metadata)
    except SchemaError as exc:
        add("error", "SCHEMA", str(exc))
        return issues
    if meta.source_dataset is not SourceDataset.STAGED:
        add("error", "NOT_STAGED", f"source_dataset is {meta.source_dataset.value!r}, expected 'staged'")
    if not PARTICIPANT_ID_RE.match(meta.participant_id):
        add("warning", "ID_CONVENTION", f"participant_id {meta.participant_id!r} does not follow P### (e.g. P001)")
    if not INTERVIEW_ID_RE.match(meta.interview_id):
        add("warning", "ID_CONVENTION", f"interview_id {meta.interview_id!r} does not follow STG-P###-S##")

    multi = len(meta.questions) > 1
    windows = []
    for q in meta.questions:
        qid = q.question_id
        if not QUESTION_ID_RE.match(qid):
            add("warning", "ID_CONVENTION", f"question_id {qid!r} does not follow Q## (e.g. Q01)")
        if multi and (q.answer_start is None or q.answer_end is None):
            add("error", "MISSING_ANSWER_WINDOW", f"{qid}: answer_start/answer_end required when a recording has "
                                                  "several questions")
        if q.question_end is None:
            add("warning", "MISSING_QUESTION_END", f"{qid}: no question_end, so response_latency will be null")
        if q.question_end is not None and q.answer_start is not None and q.answer_start < q.question_end:
            add("warning", "ANSWER_BEFORE_QUESTION_END", f"{qid}: answer_start is before question_end")
        if q.assistance_label in AI_LABELS:
            if not q.ai_model_used:
                add("warning", "MISSING_AI_METADATA", f"{qid}: {q.assistance_label.value} without ai_model_used")
            if not q.ai_prompt_used:
                add("warning", "MISSING_AI_METADATA", f"{qid}: {q.assistance_label.value} without ai_prompt_used")
            if not q.generated_ai_answer:
                add("warning", "MISSING_AI_METADATA", f"{qid}: {q.assistance_label.value} without generated_ai_answer")
        if q.assistance_label is AssistanceLabel.HUMAN_UNASSISTED and (q.ai_model_used or q.generated_ai_answer):
            add("warning", "AI_METADATA_ON_HUMAN_ANSWER",
                f"{qid}: HUMAN_UNASSISTED answer has AI metadata; fine if generated only for comparison, "
                "otherwise check the label")
        if q.answer_start is not None and q.answer_end is not None:
            windows.append((q.answer_start, q.answer_end, qid))

    windows.sort()
    for (s1, e1, a), (s2, e2, b) in zip(windows, windows[1:]):
        if s2 < e1:
            add("error", "OVERLAPPING_ANSWERS", f"answer windows of {a} and {b} overlap")
    return issues
