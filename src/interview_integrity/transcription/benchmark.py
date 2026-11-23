"""STT benchmark: run several candidate transcribers on the same clips and compare.

Measured per candidate: corpus WER, filler recall, word-timestamp coverage, speaker-label
coverage, processing speed (real-time factor) and peak process memory. Static factors
(privacy, cost, local vs hosted) come from the candidate config so the report holds
everything the STT decision needs.

Heavy: running real candidates downloads/loads models. Run on a machine with disk space
(docs/teammate-validation.md). Unit tests use fake transcribers.
"""

from __future__ import annotations

import json
import logging
import resource
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .base import Transcriber, Transcript
from .evaluate import score_transcript, summarize_scores

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Candidate:
    name: str
    transcriber: str  # registry name
    options: dict[str, Any] = field(default_factory=dict)
    runs_locally: bool = True
    sends_audio_externally: bool = False
    cost_note: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Candidate":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Clip:
    clip_id: str
    audio_path: Path
    reference: Transcript
    audio_seconds: float


def load_candidates(path: str | Path) -> list[Candidate]:
    data = json.loads(Path(path).read_text())
    return [Candidate.from_dict(c) for c in data["candidates"]]


def _peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 2**20 if sys.platform == "darwin" else rss / 1024  # bytes on macOS, KiB on Linux


def run_benchmark(
    candidates: Iterable[Candidate],
    clips: list[Clip],
    factory: Callable[..., Transcriber],
    *,
    allow_external_upload: bool = False,
) -> dict[str, Any]:
    """``factory(name, **options)`` builds a transcriber (normally ``registry.create_transcriber``)."""
    results = []
    for cand in candidates:
        entry: dict[str, Any] = {"candidate": asdict(cand), "status": "ok"}
        if cand.sends_audio_externally and not allow_external_upload:
            entry.update(status="skipped", reason="sends audio to a third party; external upload not approved")
            results.append(entry)
            continue
        try:
            t0 = time.perf_counter()
            transcriber = factory(cand.transcriber, **cand.options)
            load_seconds = time.perf_counter() - t0
        except Exception as exc:  # missing package / model: report, don't crash the whole benchmark
            entry.update(status="unavailable", reason=f"{type(exc).__name__}: {exc}")
            results.append(entry)
            continue

        scores, speaker_clips, wall, audio, failures = [], 0, 0.0, 0.0, {}
        for clip in clips:
            t0 = time.perf_counter()
            try:
                hyp = transcriber.transcribe(clip.audio_path)
            except Exception as exc:
                failures[clip.clip_id] = f"{type(exc).__name__}: {exc}"
                continue
            wall += time.perf_counter() - t0
            audio += clip.audio_seconds
            scores.append(score_transcript(clip.clip_id, clip.reference, hyp))
            speaker_clips += any(s.speaker for s in hyp.segments)
            log.info("%s: %s done", cand.name, clip.clip_id)

        summary = summarize_scores(scores) if scores else {"clips": 0}
        entry.update(
            model_load_seconds=round(load_seconds, 2),
            audio_seconds=round(audio, 2),
            transcribe_seconds=round(wall, 2),
            real_time_factor=round(wall / audio, 3) if audio else None,  # < 1 means faster than real time
            speaker_label_coverage=round(speaker_clips / len(scores), 4) if scores else None,
            peak_process_rss_mb=round(_peak_rss_mb(), 1),
            failures=failures,
            **{k: v for k, v in summary.items() if k != "per_clip"},
            per_clip=summary.get("per_clip", []),
        )
        results.append(entry)
    return {
        "clips": [c.clip_id for c in clips],
        "note": "peak_process_rss_mb is cumulative for the benchmark process; run one candidate per "
                "process for a clean memory figure.",
        "results": results,
    }
