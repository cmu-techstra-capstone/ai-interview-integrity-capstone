/**
 * API-facing analysis contract (analysis.v1), mirrored from Python
 * `interview_integrity.analysis_contract`.
 *
 * Transport-neutral: HTTP/fetch is not required to map this into overlay view models.
 * Do not treat EvidenceSignal / descriptive features as AI-assistance proof.
 */

export const ANALYSIS_SCHEMA_VERSION = "analysis.v1" as const;

export type AnalysisDataOrigin = "offline_processing" | "demo";

export type ProcessingState = "completed" | "completed_with_warnings" | "failed";

export type TranscriptMode = "sidecar" | "stt" | "none";

export type DetectionStatus =
  | "model_unavailable"
  | "insufficient_evidence"
  | "model_error"
  | "inference_available";

export type ConfidenceStatus =
  | "unavailable_not_calibrated"
  | "unavailable_not_provided"
  | "provided";

export interface AnalysisProvenance {
  schema_version: string;
  analysis_id: string;
  source: AnalysisDataOrigin;
  is_synthetic: boolean;
  transcript_mode: TranscriptMode;
  stt_requested: string | null;
  stt_options?: Record<string, unknown>;
  video_path?: string | null;
  metadata_ref?: string | null;
  transcript_path?: string | null;
  pipeline?: string;
}

export interface ContractTranscriptSegment {
  id: string;
  text: string;
  start_seconds: number | null;
  end_seconds: number | null;
  speaker: string | null;
  words?: Array<Record<string, unknown>>;
}

export interface EvidenceSignalDict {
  signal_name: string;
  modality: string;
  value: string | number | boolean | null;
  quality_status: string;
  explanation: string;
  sample_key: string;
  confidence?: number | null;
  supporting_timestamps?: Array<[number, number] | number[]>;
  supporting_transcript_span?: {
    text: string;
    start: number | null;
    end: number | null;
  } | null;
  source_features?: string[];
}

export interface AnswerAnalysisRecord {
  interview_id: string;
  participant_id: string;
  question_id: string;
  recording_id: string;
  question_text: string | null;
  transcript: string | null;
  question_start: number | null;
  question_end: number | null;
  answer_start: number | null;
  answer_end: number | null;
  response_latency: number | null;
  answer_duration: number | null;
  transcript_segments: ContractTranscriptSegment[];
  has_word_timestamps: boolean;
  has_segment_timestamps: boolean;
  audio_timing_features: Record<string, unknown>;
  linguistic_features: Record<string, unknown>;
  recording_quality_features: Record<string, unknown>;
  provenance_features: Record<string, unknown>;
  evidence_signals: EvidenceSignalDict[];
  sample_row: Record<string, unknown>;
}

export interface QualityIssueDict {
  severity: string;
  code: string;
  key: string;
  message: string;
}

export interface DetectionContract {
  status: DetectionStatus;
  message: string;
  confidence_status: ConfidenceStatus;
  confidence_value: number | null;
  calibrated: boolean | null;
  model_name: string | null;
  model_version: string | null;
  review_label: string | null;
  review_status: string | null;
  raw_score: number | null;
  detection_evidence: Array<Record<string, unknown>>;
  related_question_id: string | null;
  warnings: string[];
  error: string | null;
}

export interface OfflineAnalysisDocument {
  schema_version: string;
  analysis_id: string;
  processing_state: ProcessingState;
  source: AnalysisDataOrigin;
  is_synthetic: boolean;
  provenance: AnalysisProvenance;
  answers: AnswerAnalysisRecord[];
  quality_issues: QualityIssueDict[];
  detection: DetectionContract;
  errors: string[];
  processing_error: string | null;
}
