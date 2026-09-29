"""Read/write processed samples.

``samples.jsonl`` is the canonical store (one JSON object per line, lossless for
``None`` values). ``samples.csv`` is a flat convenience export regenerated from it.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .schema import CORE_COLUMNS, InterviewSample


def load_jsonl(path: str | Path) -> list[InterviewSample]:
    path = Path(path)
    if not path.exists():
        return []
    samples = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            try:
                samples.append(InterviewSample.from_row(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"{path}:{lineno}: invalid sample: {exc}") from exc
    return samples


def write_jsonl(samples: Iterable[InterviewSample], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for s in samples:
            fh.write(json.dumps(s.to_row()) + "\n")


def upsert_jsonl(new: Iterable[InterviewSample], path: str | Path) -> list[InterviewSample]:
    """Insert or replace samples by (recording_id, question_id, augmentation)."""
    merged = {s.key: s for s in load_jsonl(path)}
    for s in new:
        merged[s.key] = s
    samples = list(merged.values())
    write_jsonl(samples, path)
    return samples


def write_csv(samples: Iterable[InterviewSample], path: str | Path) -> None:
    rows = [s.to_row() for s in samples]
    feature_cols = sorted({k for r in rows for k in r} - set(CORE_COLUMNS))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[*CORE_COLUMNS, *feature_cols])
        writer.writeheader()
        for r in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in r.items()})
