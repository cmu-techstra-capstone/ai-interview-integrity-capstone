/**
 * Typed local API client. Transport-injectable for tests.
 * Does not perform browser media capture.
 */

import type { OfflineAnalysisDocument } from "../types/analysisContract";
import {
  assertLoopbackApiBaseUrl,
  DEFAULT_API_CONFIG,
  isSafeRelativePath,
  type ApiClientConfig,
} from "./config";
import type { AnalyzeOfflineRequestPayload, AnalyzeResult, HealthResult } from "./types";

export type FetchLike = typeof fetch;

export class LocalApiClient {
  readonly config: ApiClientConfig;
  private readonly fetchImpl: FetchLike;

  constructor(config: Partial<ApiClientConfig> = {}, fetchImpl: FetchLike = fetch) {
    this.config = { ...DEFAULT_API_CONFIG, ...config };
    this.fetchImpl = fetchImpl;
    assertLoopbackApiBaseUrl(this.config.apiBaseUrl, this.config.allowedHosts);
  }

  private url(path: string): string {
    const base = assertLoopbackApiBaseUrl(this.config.apiBaseUrl, this.config.allowedHosts);
    return new URL(path, base).toString();
  }

  async health(signal?: AbortSignal): Promise<HealthResult> {
    try {
      const res = await this.fetchImpl(this.url("/health"), {
        method: "GET",
        headers: { Accept: "application/json" },
        signal,
      });
      if (!res.ok) {
        return {
          ok: false,
          error: { code: "backend_unavailable", message: `Health check failed (${res.status})` },
        };
      }
      const data = (await res.json()) as {
        ok?: boolean;
        detection_model?: string;
        recordings_dir_configured?: boolean;
      };
      return {
        ok: true,
        detectionModel: data.detection_model || "unavailable",
        recordingsDirConfigured: Boolean(data.recordings_dir_configured),
      };
    } catch {
      return {
        ok: false,
        error: {
          code: "backend_unavailable",
          message: "Local API is unreachable. Is the localhost server running?",
        },
      };
    }
  }

  async analyzeOffline(
    payload: AnalyzeOfflineRequestPayload,
    signal?: AbortSignal,
  ): Promise<AnalyzeResult> {
    if (!isSafeRelativePath(payload.recordingRelpath)) {
      return {
        ok: false,
        error: {
          code: "validation_error",
          message: "recordingRelpath must be a relative path without '..'",
        },
      };
    }
    if (!isSafeRelativePath(payload.metadataRelpath)) {
      return {
        ok: false,
        error: {
          code: "validation_error",
          message: "metadataRelpath must be a relative path without '..'",
        },
      };
    }
    if (payload.transcriptRelpath && !isSafeRelativePath(payload.transcriptRelpath)) {
      return {
        ok: false,
        error: {
          code: "validation_error",
          message: "transcriptRelpath must be a relative path without '..'",
        },
      };
    }

    const body = {
      recording_relpath: payload.recordingRelpath.trim(),
      metadata_relpath: payload.metadataRelpath.trim(),
      transcript_relpath: payload.transcriptRelpath?.trim() || null,
      stt: payload.stt?.trim() || null,
    };

    try {
      const res = await this.fetchImpl(this.url("/v1/analyze-offline"), {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      });
      const data = (await res.json()) as {
        ok?: boolean;
        analysis?: OfflineAnalysisDocument;
        error?: { code?: string; message?: string };
      };

      if (res.status === 422 && data.analysis) {
        return {
          ok: false,
          error: {
            code: data.error?.code || "processing_failed",
            message: data.error?.message || "Offline processing failed",
          },
          analysis: data.analysis,
        };
      }

      if (!res.ok || data.ok === false) {
        return {
          ok: false,
          error: {
            code: data.error?.code || "analysis_failed",
            message: data.error?.message || `Request failed (${res.status})`,
          },
          analysis: data.analysis,
        };
      }

      if (!data.analysis || data.analysis.schema_version !== "analysis.v1") {
        return {
          ok: false,
          error: {
            code: "invalid_response",
            message: "API returned an unexpected analysis payload",
          },
        };
      }

      return { ok: true, analysis: data.analysis };
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return {
          ok: false,
          error: { code: "aborted", message: "Request was cancelled" },
        };
      }
      return {
        ok: false,
        error: {
          code: "backend_unavailable",
          message: "Local API is unreachable. Is the localhost server running?",
        },
      };
    }
  }
}
