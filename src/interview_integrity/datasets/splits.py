"""Group-aware train/val/test splitting.

All samples sharing a group (by default the participant) land in the same split.
Because augmented variants carry the same participant_id and recording_id as
their original, they can never leak across partitions.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from .schema import InterviewSample

DEFAULT_RATIOS = {"train": 0.7, "val": 0.15, "test": 0.15}


def _group_counts(n_groups: int, ratios: dict[str, float]) -> dict[str, int]:
    total = sum(ratios.values())
    exact = {k: n_groups * v / total for k, v in ratios.items()}
    counts = {k: int(x) for k, x in exact.items()}
    for k in sorted(exact, key=lambda k: exact[k] - counts[k], reverse=True)[: n_groups - sum(counts.values())]:
        counts[k] += 1
    # With enough groups, make sure every requested split is non-empty.
    if n_groups >= len(ratios):
        for k in ratios:
            if counts[k] == 0 and ratios[k] > 0:
                donor = max(counts, key=counts.get)  # type: ignore[arg-type]
                counts[donor] -= 1
                counts[k] += 1
    return counts


def assign_splits(
    samples: Iterable[InterviewSample],
    ratios: dict[str, float] | None = None,
    *,
    seed: int = 13,
    group_key: str = "participant_id",
) -> list[InterviewSample]:
    samples = list(samples)
    ratios = ratios or DEFAULT_RATIOS
    groups = sorted({str(getattr(s, group_key)) for s in samples})
    random.Random(seed).shuffle(groups)

    assignment: dict[str, str] = {}
    i = 0
    for split, count in _group_counts(len(groups), ratios).items():
        for g in groups[i : i + count]:
            assignment[g] = split
        i += count
    return [replace(s, split=assignment[str(getattr(s, group_key))]) for s in samples]


def find_group_leakage(
    samples: Iterable[InterviewSample], group_key: str = "participant_id"
) -> dict[str, set[str]]:
    """Return groups that appear in more than one split (empty dict == no leakage)."""
    seen: dict[str, set[str]] = defaultdict(set)
    for s in samples:
        if s.split:
            seen[str(getattr(s, group_key))].add(s.split)
    return {g: splits for g, splits in seen.items() if len(splits) > 1}
