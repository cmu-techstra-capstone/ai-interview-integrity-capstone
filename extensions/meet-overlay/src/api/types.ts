import type { OfflineAnalysisDocument } from "../types/analysisContract";

export type ConnectionState =
  | "disconnected"
  | "connecting"
  | "processing"
  | "completed"
  | "validation_error"
  | "backend_unavailable"
  | "analysis_failed";

export type AnalyzeOfflineRequestPayload = {
  recordingRelpath: string;
  metadataRelpath: string;
  transcriptRelpath?: string;
  stt?: string;
};

export type ApiErrorPayload = {
  code: string;
  message: string;
};

export type HealthResult =
  | { ok: true; detectionModel: string; recordingsDirConfigured: boolean }
  | { ok: false; error: ApiErrorPayload };

export type AnalyzeResult =
  | { ok: true; analysis: OfflineAnalysisDocument }
  | { ok: false; error: ApiErrorPayload; analysis?: OfflineAnalysisDocument };
