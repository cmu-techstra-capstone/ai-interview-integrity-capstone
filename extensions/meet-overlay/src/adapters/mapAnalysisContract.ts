/**
 * Transport-neutral mapping from analysis.v1 → overlay presentation types.
 * Does not fetch over HTTP; callers supply an OfflineAnalysisDocument (file, mock, or future API).
 */

import type { OfflineAnalysisDocument, EvidenceSignalDict } from "../types/analysisContract";
import type {
  ConfidenceAvailability,
  DataSource,
  DetectionPrediction,
  DetectionResultState,
  InterviewQuestion,
  QualityWarning,
  SupportingEvidence,
  TranscriptSegment,
} from "../types/session";

export type OverlayPanelModel = {
  source: DataSource;
  modeLabel: "DEMO SIMULATION" | "OFFLINE ANALYSIS";
  meetContext: string;
  analysisId: string | null;
  question: InterviewQuestion | null;
  questionVisible: boolean;
  candidateResponding: boolean;
  revealedSegments: TranscriptSegment[];
  detection: DetectionResultState;
  /** Descriptive offline features — not model detection output. */
  descriptiveEvidence: SupportingEvidence[];
  qualityWarnings: QualityWarning[];
  isSynthetic: boolean;
  processingError: string | null;
};

function humanizeSignalName(name: string): string {
  return name.replace(/_/g, " ");
}

function mapConfidence(detection: OfflineAnalysisDocument["detection"]): ConfidenceAvailability {
  if (detection.confidence_status === "provided" && detection.confidence_value != null) {
    return {
      status: "provided",
      value: detection.confidence_value,
      calibrated: Boolean(detection.calibrated),
      note: detection.calibrated
        ? undefined
        : "Score provided but not marked calibrated — do not treat as a cheating probability.",
    };
  }
  if (detection.confidence_status === "unavailable_not_provided") {
    return { status: "unavailable", reason: "not_provided" };
  }
  return { status: "unavailable", reason: "not_calibrated" };
}

function mapEvidenceSignal(
  signal: EvidenceSignalDict,
  index: number,
  category: SupportingEvidence["category"],
): SupportingEvidence {
  return {
    id: `ev-${signal.signal_name}-${index}`,
    category,
    title: humanizeSignalName(signal.signal_name),
    description: signal.explanation,
    signalName: signal.signal_name,
    modality: signal.modality as SupportingEvidence["modality"],
    qualityStatus: signal.quality_status as SupportingEvidence["qualityStatus"],
  };
}

export function mapQualityWarnings(doc: OfflineAnalysisDocument): QualityWarning[] {
  return doc.quality_issues.map((issue, i) => ({
    id: `qw-${issue.code}-${i}`,
    code: issue.code,
    message: issue.message,
  }));
}

export function mapDescriptiveEvidence(doc: OfflineAnalysisDocument): SupportingEvidence[] {
  const answer = doc.answers[0];
  if (!answer) return [];
  return answer.evidence_signals.map((s, i) => mapEvidenceSignal(s, i, "audio_linguistic"));
}

export function mapTranscriptSegments(doc: OfflineAnalysisDocument): TranscriptSegment[] {
  const answer = doc.answers[0];
  if (!answer) return [];
  return answer.transcript_segments.map((seg) => ({
    id: seg.id,
    speaker: seg.speaker || "Candidate",
    startSeconds: seg.start_seconds ?? answer.answer_start ?? 0,
    text: seg.text,
  }));
}

export function mapInterviewQuestion(doc: OfflineAnalysisDocument): InterviewQuestion | null {
  const answer = doc.answers[0];
  if (!answer) return null;
  return {
    id: answer.question_id,
    text: answer.question_text || "(question text unavailable)",
    askedAtLabel:
      answer.question_start != null ? `t=${answer.question_start.toFixed(1)}s` : undefined,
  };
}

function mapReviewStatus(
  value: string | null,
): DetectionPrediction["reviewStatus"] {
  if (value === "Requires review" || value === "No elevated signal" || value === "Insufficient evidence") {
    return value;
  }
  return "Insufficient evidence";
}

export function mapDetectionResultState(doc: OfflineAnalysisDocument): DetectionResultState {
  if (doc.processing_state === "failed" && doc.processing_error) {
    return {
      kind: "failed",
      message: `Offline processing failed: ${doc.processing_error}`,
    };
  }

  const detection = doc.detection;
  switch (detection.status) {
    case "model_unavailable":
      return { kind: "model_unavailable", message: detection.message };
    case "insufficient_evidence":
      return { kind: "insufficient_evidence", message: detection.message };
    case "model_error":
      return {
        kind: "failed",
        message: detection.error
          ? `${detection.message} (${detection.error})`
          : detection.message,
      };
    case "inference_available": {
      const prediction: DetectionPrediction = {
        schemaVersion: doc.schema_version,
        reviewLabel:
          detection.review_label ||
          "Model output available for human review — not an automated cheating verdict.",
        reviewStatus: mapReviewStatus(detection.review_status),
        rawScore: detection.raw_score,
        confidence: mapConfidence(detection),
        evidence: [
          ...detection.detection_evidence.map((raw, i) => ({
            id: `det-${i}`,
            category: "detection" as const,
            title: String(raw.title ?? raw.signal_name ?? `Detection signal ${i + 1}`),
            description: String(raw.description ?? raw.explanation ?? ""),
            signalName: raw.signal_name ? String(raw.signal_name) : undefined,
          })),
          ...mapDescriptiveEvidence(doc),
        ],
        relatedQuestionId: detection.related_question_id || doc.answers[0]?.question_id || "",
        model: {
          name: detection.model_name || "unknown",
          version: detection.model_version || "unknown",
          note:
            detection.message ||
            "Inference from an approved detection adapter — confidence may still be unavailable.",
        },
        warnings: [
          ...(detection.warnings || []),
          "Do not interpret raw scores as a calibrated cheating probability.",
        ],
      };
      return { kind: "available", prediction };
    }
    default:
      return { kind: "no_result" };
  }
}

/**
 * Build the overlay panel model from a backend-shaped analysis document.
 * Demo mode remains independent — this path always sets source from the document.
 */
export function mapOfflineAnalysisToPanelModel(
  doc: OfflineAnalysisDocument,
  options?: { meetContext?: string },
): OverlayPanelModel {
  const source: DataSource = doc.source === "demo" || doc.is_synthetic ? "demo" : "backend";
  const detection = mapDetectionResultState(doc);
  const qualityWarnings = mapQualityWarnings(doc);
  const descriptiveEvidence = mapDescriptiveEvidence(doc);

  return {
    source,
    modeLabel: source === "demo" ? "DEMO SIMULATION" : "OFFLINE ANALYSIS",
    meetContext:
      options?.meetContext ||
      (source === "demo"
        ? "Synthetic demonstration — not live Meet audio."
        : "Offline processed recording — not live Meet capture."),
    analysisId: doc.analysis_id,
    question: mapInterviewQuestion(doc),
    questionVisible: Boolean(doc.answers[0]),
    candidateResponding: false,
    revealedSegments: mapTranscriptSegments(doc),
    detection,
    descriptiveEvidence,
    qualityWarnings,
    isSynthetic: doc.is_synthetic,
    processingError: doc.processing_error,
  };
}
