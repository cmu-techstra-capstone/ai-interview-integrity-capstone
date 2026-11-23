"""Independent research-model boundaries for live mode (honest unavailable stubs).

Does not merge PR #9 / #11. Does not fabricate scores or cheating probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResearchModelResult:
    model_id: str
    research_target: str
    status: str  # available | model_unavailable | insufficient_evidence | failed
    label: str | None
    evidence: str
    raw_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "research_target": self.research_target,
            "status": self.status,
            "label": self.label,
            "evidence": self.evidence,
            "raw_score": self.raw_score,
            # Explicitly not a cheating / rejection signal.
            "is_cheating_probability": False,
        }


class AudioDeliveryResearchAdapter:
    """Intended: reading-like vs spontaneous (e.g. ALLSSTAR). Artifacts not in this branch."""

    model_id = "audio-delivery-research"
    research_target = "reading_vs_spontaneous_delivery"

    def infer(self, *, speech_seconds: float, feature_summary: dict[str, Any] | None = None) -> ResearchModelResult:
        del feature_summary
        if speech_seconds < 3.0:
            return ResearchModelResult(
                model_id=self.model_id,
                research_target=self.research_target,
                status="insufficient_evidence",
                label=None,
                evidence="Need a longer reliably attributed speech window before delivery research.",
            )
        return ResearchModelResult(
            model_id=self.model_id,
            research_target=self.research_target,
            status="model_unavailable",
            label=None,
            evidence=(
                "ALLSSTAR / delivery research artifacts are not bundled on this branch. "
                "No live delivery score is produced."
            ),
        )


class TranscriptAuthorshipResearchAdapter:
    """Intended: AI-authored vs human-authored text patterns (e.g. HANSEN TF-IDF)."""

    model_id = "transcript-authorship-research"
    research_target = "ai_vs_human_written_text"

    def infer(self, *, transcript_text: str) -> ResearchModelResult:
        words = [w for w in transcript_text.split() if w]
        if len(words) < 20:
            return ResearchModelResult(
                model_id=self.model_id,
                research_target=self.research_target,
                status="insufficient_evidence",
                label=None,
                evidence="Need more transcript text before authorship research is meaningful.",
            )
        return ResearchModelResult(
            model_id=self.model_id,
            research_target=self.research_target,
            status="model_unavailable",
            label=None,
            evidence=(
                "HANSEN / text-authorship research artifacts are not bundled on this branch. "
                "No live authorship score is produced."
            ),
        )
