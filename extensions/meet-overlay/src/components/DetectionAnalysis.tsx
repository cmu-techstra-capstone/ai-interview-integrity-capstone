import type {
  ConfidenceAvailability,
  DataSource,
  DetectionResultState,
  QualityWarning,
  SupportingEvidence,
} from "../types/session";

type Props = {
  detection: DetectionResultState;
  qualityWarnings: QualityWarning[];
  /** When omitted, treated as demo (preserves Phase 2 behavior). */
  dataSource?: DataSource;
  /**
   * Descriptive offline features (audio/linguistic). Shown separately from
   * model detection evidence — never presented as proof of AI assistance.
   */
  descriptiveEvidence?: SupportingEvidence[];
};

function EvidenceList({
  title,
  items,
}: {
  title: string;
  items: SupportingEvidence[];
}) {
  if (!items.length) return null;
  return (
    <div className="ii-evidence-group">
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <strong>{item.title}</strong>
            <p>{item.description}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function confidenceLabel(confidence: ConfidenceAvailability): string {
  if (confidence.status === "provided") {
    const cal = confidence.calibrated ? "calibrated" : "not calibrated";
    return `${(confidence.value * 100).toFixed(0)}% (${cal})`;
  }
  if (confidence.reason === "demo") return "Not calibrated / unavailable (demo)";
  if (confidence.reason === "not_provided") return "Not provided";
  return "Not calibrated / unavailable";
}

export function DetectionAnalysis({
  detection,
  qualityWarnings,
  dataSource = "demo",
  descriptiveEvidence = [],
}: Props) {
  const sourcePill = dataSource === "demo" ? "Demo fixture" : "Offline analysis";

  return (
    <section className="ii-section" aria-label="Detection analysis">
      <div className="ii-section-head">
        <h2>Detection analysis</h2>
        <span
          className={`ii-pill ${dataSource === "demo" ? "ii-pill-demo" : "ii-pill-offline"}`}
        >
          {sourcePill}
        </span>
      </div>

      {detection.kind === "no_result" && (
        <p className="ii-empty">
          {dataSource === "demo"
            ? "No result yet — waiting for the demo analysis step."
            : "No detection result yet."}
        </p>
      )}

      {detection.kind === "processing" && (
        <p className="ii-status-processing" role="status">
          {detection.message}
        </p>
      )}

      {detection.kind === "insufficient_evidence" && (
        <p className="ii-status-warn">{detection.message}</p>
      )}

      {detection.kind === "model_unavailable" && (
        <p className="ii-status-warn">{detection.message}</p>
      )}

      {detection.kind === "failed" && (
        <p className="ii-status-error">{detection.message}</p>
      )}

      {detection.kind === "available" && (
        <div className="ii-detection">
          <p className="ii-review-status">
            Status: <strong>{detection.prediction.reviewStatus}</strong>
          </p>
          <p className="ii-review-label">{detection.prediction.reviewLabel}</p>
          <p className="ii-confidence">
            Confidence: <strong>{confidenceLabel(detection.prediction.confidence)}</strong>
          </p>
          <p className="ii-meta">
            {detection.prediction.model.note} · schema{" "}
            {detection.prediction.schemaVersion}
          </p>
          {detection.prediction.warnings.map((w) => (
            <p key={w} className="ii-banner">
              {w}
            </p>
          ))}
          <EvidenceList
            title="Detection evidence"
            items={detection.prediction.evidence.filter((e) => e.category === "detection")}
          />
          <EvidenceList
            title="Audio / linguistic evidence"
            items={detection.prediction.evidence.filter(
              (e) => e.category === "audio_linguistic",
            )}
          />
          <EvidenceList
            title="Recording-quality notes"
            items={detection.prediction.evidence.filter(
              (e) => e.category === "recording_quality",
            )}
          />
        </div>
      )}

      {descriptiveEvidence.length > 0 && detection.kind !== "available" && (
        <EvidenceList
          title="Descriptive features (not model output)"
          items={descriptiveEvidence}
        />
      )}

      {qualityWarnings.length > 0 && (
        <div className="ii-quality-block">
          <h3>Quality warnings</h3>
          <ul>
            {qualityWarnings.map((w) => (
              <li key={w.id}>
                <code>{w.code}</code> — {w.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
