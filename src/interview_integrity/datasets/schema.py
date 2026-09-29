"""Data model for interview samples.

Conventions
-----------
* One ``InterviewSample`` == one answer to one question in one recording.
* All times are in **seconds**, relative to the start of the recording.
* Unknown values are ``None`` (numbers/text) or ``UNKNOWN`` (labels). Never invent them.
* ``assistance_label`` (how the answer was produced) and ``deception_label``
  (whether the content was truthful) are independent axes. Public deception
  datasets must never carry an assistance label derived from their deception label.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


class SchemaError(ValueError):
    """Raised when metadata or a sample violates the dataset schema."""


class AssistanceLabel(str, enum.Enum):
    HUMAN_UNASSISTED = "HUMAN_UNASSISTED"
    AI_ASSISTED = "AI_ASSISTED"
    AI_VERBATIM = "AI_VERBATIM"
    AI_PERSONALIZED = "AI_PERSONALIZED"
    UNKNOWN = "UNKNOWN"


class DeceptionLabel(str, enum.Enum):
    TRUTHFUL = "TRUTHFUL"
    DECEPTIVE = "DECEPTIVE"
    UNKNOWN = "UNKNOWN"


class SourceDataset(str, enum.Enum):
    STAGED = "staged"
    DOLOS = "dolos"
    REAL_LIFE_DECEPTION = "real_life_deception"
    BAG_OF_LIES = "bag_of_lies"
    OTHER = "other"


# Datasets whose ground truth is about deception, not AI assistance.
DECEPTION_ONLY_DATASETS = frozenset(
    {SourceDataset.DOLOS, SourceDataset.REAL_LIFE_DECEPTION, SourceDataset.BAG_OF_LIES}
)


def _parse_enum(enum_cls: type[enum.Enum], value: Any, field_name: str, default: Any = None):
    if value is None or (isinstance(value, str) and value.strip() == ""):
        if default is not None:
            return default
        raise SchemaError(f"'{field_name}' is required")
    if isinstance(value, enum_cls):
        return value
    text = str(value).strip()
    for member in enum_cls:
        if text.upper() == member.value.upper() or text.upper() == member.name:
            return member
    allowed = ", ".join(m.value for m in enum_cls)
    raise SchemaError(f"Invalid {field_name} {value!r}; expected one of: {allowed}")


def _parse_time(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        t = float(value)
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"'{field_name}' must be a number of seconds, got {value!r}") from exc
    if t < 0:
        raise SchemaError(f"'{field_name}' must be >= 0, got {t}")
    return t


def _require_id(value: Any, field_name: str) -> str:
    if value is None or str(value).strip() == "":
        raise SchemaError(f"'{field_name}' is required")
    return str(value).strip()


def _check_label_separation(source: SourceDataset, assistance: AssistanceLabel, where: str) -> None:
    if source in DECEPTION_ONLY_DATASETS and assistance is not AssistanceLabel.UNKNOWN:
        raise SchemaError(
            f"{where}: source_dataset '{source.value}' has deception labels only; "
            f"assistance_label must be UNKNOWN (got {assistance.value}). "
            "Do not derive AI-assistance labels from deception labels."
        )


def _check_window(start: float | None, end: float | None, where: str) -> None:
    if start is not None and end is not None and end <= start:
        raise SchemaError(f"{where}: answer_end ({end}) must be greater than answer_start ({start})")


@dataclass
class QuestionSpec:
    """One question/answer pair within a recording, as described by metadata."""

    question_id: str
    question_text: str | None = None
    question_end: float | None = None
    answer_start: float | None = None
    answer_end: float | None = None
    assistance_label: AssistanceLabel = AssistanceLabel.UNKNOWN
    deception_label: DeceptionLabel = DeceptionLabel.UNKNOWN

    @classmethod
    def from_dict(cls, data: dict[str, Any], defaults: dict[str, Any] | None = None) -> "QuestionSpec":
        merged = {**(defaults or {}), **data}
        spec = cls(
            question_id=_require_id(merged.get("question_id"), "question_id"),
            question_text=merged.get("question_text") or None,
            question_end=_parse_time(merged.get("question_end"), "question_end"),
            answer_start=_parse_time(merged.get("answer_start"), "answer_start"),
            answer_end=_parse_time(merged.get("answer_end"), "answer_end"),
            assistance_label=_parse_enum(
                AssistanceLabel, merged.get("assistance_label"), "assistance_label", AssistanceLabel.UNKNOWN
            ),
            deception_label=_parse_enum(
                DeceptionLabel, merged.get("deception_label"), "deception_label", DeceptionLabel.UNKNOWN
            ),
        )
        _check_window(spec.answer_start, spec.answer_end, f"question {spec.question_id}")
        return spec


@dataclass
class RecordingMetadata:
    """Metadata for one source recording (video), possibly containing several answers.

    Accepted JSON shapes::

        # one answer per video: question fields at top level
        {"interview_id": "INT001", "participant_id": "P001", "source_dataset": "staged",
         "question_id": "Q01", "assistance_label": "HUMAN_UNASSISTED"}

        # several answers per video
        {"interview_id": "INT001", "participant_id": "P001", "source_dataset": "staged",
         "questions": [{"question_id": "Q01", "answer_start": 3.0, "answer_end": 40.0}, ...]}

    Top-level label fields act as defaults for every entry in ``questions``.
    """

    interview_id: str
    participant_id: str
    source_dataset: SourceDataset
    questions: list[QuestionSpec]
    recording_id: str = ""
    augmentation: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    _KNOWN_KEYS = frozenset(
        {"interview_id", "participant_id", "source_dataset", "questions", "recording_id", "augmentation"}
    )
    _QUESTION_KEYS = frozenset(f.name for f in fields(QuestionSpec))

    def __post_init__(self) -> None:
        if not self.recording_id:
            self.recording_id = self.interview_id

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecordingMetadata":
        if not isinstance(data, dict):
            raise SchemaError("Recording metadata must be a JSON object")
        interview_id = _require_id(data.get("interview_id"), "interview_id")
        participant_id = _require_id(data.get("participant_id"), "participant_id")
        source = _parse_enum(SourceDataset, data.get("source_dataset"), "source_dataset")

        defaults = {k: v for k, v in data.items() if k in cls._QUESTION_KEYS}
        raw_questions = data.get("questions")
        if raw_questions is None:
            questions = [QuestionSpec.from_dict({}, defaults)]
        else:
            if not isinstance(raw_questions, list) or not raw_questions:
                raise SchemaError("'questions' must be a non-empty list")
            questions = [QuestionSpec.from_dict(q, defaults) for q in raw_questions]

        ids = [q.question_id for q in questions]
        if len(ids) != len(set(ids)):
            raise SchemaError(f"Duplicate question_id in recording {interview_id}: {ids}")
        for q in questions:
            _check_label_separation(source, q.assistance_label, f"question {q.question_id}")

        extra = {
            k: v for k, v in data.items() if k not in cls._KNOWN_KEYS and k not in cls._QUESTION_KEYS
        }
        return cls(
            interview_id=interview_id,
            participant_id=participant_id,
            source_dataset=source,
            questions=questions,
            recording_id=str(data.get("recording_id") or interview_id),
            augmentation=data.get("augmentation") or None,
            extra=extra,
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "RecordingMetadata":
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Metadata file not found: {path}")
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise SchemaError(f"Metadata file {path} is not valid JSON: {exc}") from exc
        return cls.from_dict(data)


# Column order for tabular exports. Features are appended after these, sorted by name.
CORE_COLUMNS: tuple[str, ...] = (
    "interview_id",
    "participant_id",
    "question_id",
    "recording_id",
    "source_dataset",
    "augmentation",
    "split",
    "assistance_label",
    "deception_label",
    "video_path",
    "audio_path",
    "transcript_path",
    "question_text",
    "transcript",
    "question_end",
    "answer_start",
    "answer_end",
    "response_latency",
    "answer_duration",
)


@dataclass
class InterviewSample:
    """One structured dataset row: a single answer plus its labels and features."""

    interview_id: str
    participant_id: str
    question_id: str
    source_dataset: SourceDataset
    recording_id: str = ""
    augmentation: str | None = None
    split: str | None = None
    assistance_label: AssistanceLabel = AssistanceLabel.UNKNOWN
    deception_label: DeceptionLabel = DeceptionLabel.UNKNOWN
    video_path: str | None = None
    audio_path: str | None = None
    transcript_path: str | None = None
    question_text: str | None = None
    transcript: str | None = None
    question_end: float | None = None
    answer_start: float | None = None
    answer_end: float | None = None
    response_latency: float | None = None
    answer_duration: float | None = None
    features: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.recording_id:
            self.recording_id = self.interview_id

    def validate(self) -> "InterviewSample":
        for name in ("interview_id", "participant_id", "question_id", "recording_id"):
            setattr(self, name, _require_id(getattr(self, name), name))
        self.source_dataset = _parse_enum(SourceDataset, self.source_dataset, "source_dataset")
        self.assistance_label = _parse_enum(
            AssistanceLabel, self.assistance_label, "assistance_label", AssistanceLabel.UNKNOWN
        )
        self.deception_label = _parse_enum(
            DeceptionLabel, self.deception_label, "deception_label", DeceptionLabel.UNKNOWN
        )
        for name in ("question_end", "answer_start", "answer_end", "answer_duration"):
            setattr(self, name, _parse_time(getattr(self, name), name))
        if self.response_latency is not None:
            # Latency may legitimately be negative (candidate starts before the question ends).
            self.response_latency = float(self.response_latency)
        where = f"sample {self.recording_id}/{self.question_id}"
        _check_window(self.answer_start, self.answer_end, where)
        _check_label_separation(self.source_dataset, self.assistance_label, where)
        collisions = set(self.features) & set(CORE_COLUMNS)
        if collisions:
            raise SchemaError(f"{where}: feature names collide with core columns: {sorted(collisions)}")
        return self

    def to_row(self) -> dict[str, Any]:
        """Flatten to a single dict (core columns first, then features)."""
        row: dict[str, Any] = {}
        for name in CORE_COLUMNS:
            value = getattr(self, name)
            row[name] = value.value if isinstance(value, enum.Enum) else value
        for name in sorted(self.features):
            row[name] = self.features[name]
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "InterviewSample":
        core = {k: row.get(k) for k in CORE_COLUMNS}
        features = {k: v for k, v in row.items() if k not in CORE_COLUMNS}
        sample = cls(**core, features=features)  # type: ignore[arg-type]
        return sample.validate()

    @property
    def key(self) -> tuple[str, str, str]:
        """Unique identity of a row: recording, question, augmentation variant."""
        return (self.recording_id, self.question_id, self.augmentation or "")
