/**
 * Renders existing overlay sections from a backend-shaped OverlayPanelModel.
 * Does not replace OverlayApp's demo chrome; used for offline/contract-driven UI.
 */

import { CurrentQuestion } from "../components/CurrentQuestion";
import { DetectionAnalysis } from "../components/DetectionAnalysis";
import { LiveTranscript } from "../components/LiveTranscript";
import type { OverlayPanelModel } from "../adapters/mapAnalysisContract";

type Props = {
  model: OverlayPanelModel;
  expanded?: boolean;
};

export function OfflineAnalysisPanel({ model, expanded = false }: Props) {
  const showQuality =
    model.detection.kind === "available" ||
    model.detection.kind === "processing" ||
    model.detection.kind === "model_unavailable" ||
    model.detection.kind === "insufficient_evidence" ||
    model.detection.kind === "failed";

  return (
    <div className="ii-offline-panel" data-source={model.source}>
      <p className="ii-meta" role="status">
        {model.modeLabel}
        {model.analysisId ? ` · ${model.analysisId}` : ""}
        {model.isSynthetic ? " · synthetic" : " · offline processing"}
      </p>
      <p className="ii-meta">{model.meetContext}</p>

      {model.question && (
        <CurrentQuestion
          question={model.question}
          visible={model.questionVisible}
          candidateResponding={model.candidateResponding}
        />
      )}

      <LiveTranscript segments={model.revealedSegments} expanded={expanded} />

      <DetectionAnalysis
        detection={model.detection}
        qualityWarnings={showQuality ? model.qualityWarnings : []}
        dataSource={model.source}
        descriptiveEvidence={model.descriptiveEvidence}
      />
    </div>
  );
}
