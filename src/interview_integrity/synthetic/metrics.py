"""AUROC with a participant-grouped bootstrap (standard library only)."""

from __future__ import annotations

import random
from typing import Iterable, Sequence


def auroc(negatives: Sequence[float], positives: Sequence[float]) -> float | None:
    """P(score_pos > score_neg) + 0.5 * P(tie). None if either side is empty."""
    if not negatives or not positives:
        return None
    ranked = sorted([(s, 0) for s in negatives] + [(s, 1) for s in positives])
    rank_sum_pos, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2  # 1-based average rank of the tie block
        rank_sum_pos += avg_rank * sum(1 for k in range(i, j) if ranked[k][1] == 1)
        i = j
    n_pos, n_neg = len(positives), len(negatives)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def grouped_bootstrap_auroc(items: Iterable[tuple[str, int, float]], n_boot: int = 1000,
                            seed: int = 20261105, alpha: float = 0.05) -> dict:
    """items: (group, label 0/1, score). Groups (participants) are resampled with replacement."""
    by_group: dict[str, list[tuple[int, float]]] = {}
    for g, y, s in items:
        by_group.setdefault(g, []).append((y, s))
    def calc(groups):
        rows = [r for g in groups for r in by_group[g]]
        return auroc([s for y, s in rows if y == 0], [s for y, s in rows if y == 1])
    groups = sorted(by_group)
    point = calc(groups)
    rng = random.Random(seed)
    boots = sorted(v for v in (calc([rng.choice(groups) for _ in groups]) for _ in range(n_boot)) if v is not None)
    if point is None or not boots:
        return {"auroc": point, "ci_low": None, "ci_high": None, "groups": len(groups)}
    lo = boots[int(alpha / 2 * (len(boots) - 1))]
    hi = boots[int((1 - alpha / 2) * (len(boots) - 1))]
    return {"auroc": round(point, 4), "ci_low": round(lo, 4), "ci_high": round(hi, 4), "groups": len(groups)}
