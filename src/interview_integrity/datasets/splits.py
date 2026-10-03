"""Group-aware train/val/test splitting.

Rows are grouped so that anything that could leak stays together: rows are in the
same group if they share a participant_id, a recording_id, or a source video
checksum (video_sha256), transitively. So augmented variants (same recording_id),
repeated answers (same participant) and mislabelled rows of one recording
(same recording_id, inconsistent participant_id) can never cross partitions.
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


def leakage_groups(samples: list[InterviewSample], group_key: str = "participant_id") -> list[str]:
    """Return a group label per sample (connected components over shared identifiers)."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    nodes_per_sample = []
    for s in samples:
        nodes = [f"{group_key}:{getattr(s, group_key)}", f"recording:{s.recording_id}"]
        if s.video_sha256:
            nodes.append(f"sha:{s.video_sha256}")
        for n in nodes[1:]:
            union(nodes[0], n)
        nodes_per_sample.append(nodes[0])
    return [find(n) for n in nodes_per_sample]


def assign_splits(
    samples: Iterable[InterviewSample],
    ratios: dict[str, float] | None = None,
    *,
    seed: int = 13,
    group_key: str = "participant_id",
) -> list[InterviewSample]:
    samples = list(samples)
    ratios = ratios or DEFAULT_RATIOS
    labels = leakage_groups(samples, group_key)
    groups = sorted(set(labels))
    random.Random(seed).shuffle(groups)

    assignment: dict[str, str] = {}
    i = 0
    for split, count in _group_counts(len(groups), ratios).items():
        for g in groups[i : i + count]:
            assignment[g] = split
        i += count
    return [replace(s, split=assignment[label]) for s, label in zip(samples, labels)]


def find_group_leakage(
    samples: Iterable[InterviewSample], group_key: str = "participant_id"
) -> dict[str, set[str]]:
    """Return groups that appear in more than one split (empty dict == no leakage)."""
    seen: dict[str, set[str]] = defaultdict(set)
    for s in samples:
        if s.split:
            value = getattr(s, group_key)
            if value:
                seen[str(value)].add(s.split)
    return {g: splits for g, splits in seen.items() if len(splits) > 1}
