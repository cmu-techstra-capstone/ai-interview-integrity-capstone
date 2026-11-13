/**
 * Content-script bridge to the service worker's allowlisted localhost API proxy.
 */

import { MessageType, type ExtensionResponse } from "../types/messages";
import type { AnalyzeOfflineRequestPayload, AnalyzeResult, HealthResult } from "./types";
import type { OfflineAnalysisDocument } from "../types/analysisContract";

function send<T extends ExtensionResponse>(message: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendMessage(message, (response) => {
        const err = chrome.runtime.lastError;
        if (err) {
          reject(new Error(err.message));
          return;
        }
        resolve(response as T);
      });
    } catch (err) {
      reject(err);
    }
  });
}

export async function bridgeHealth(): Promise<HealthResult> {
  try {
    const res = await send<ExtensionResponse>({ type: MessageType.API_HEALTH });
    if (res && "ok" in res && res.ok && "kind" in res && res.kind === "health") {
      return {
        ok: true,
        detectionModel: res.detectionModel,
        recordingsDirConfigured: res.recordingsDirConfigured,
      };
    }
    if (res && "ok" in res && res.ok === false) {
      return { ok: false, error: res.error };
    }
    return {
      ok: false,
      error: { code: "backend_unavailable", message: "Unexpected health response" },
    };
  } catch {
    return {
      ok: false,
      error: {
        code: "backend_unavailable",
        message: "Could not reach the extension service worker / local API",
      },
    };
  }
}

export async function bridgeAnalyze(
  payload: AnalyzeOfflineRequestPayload,
): Promise<AnalyzeResult> {
  try {
    const res = await send<ExtensionResponse>({
      type: MessageType.API_ANALYZE,
      payload,
    });
    if (res && "ok" in res && res.ok && "kind" in res && res.kind === "analyze") {
      return { ok: true, analysis: res.analysis as OfflineAnalysisDocument };
    }
    if (res && "ok" in res && res.ok === false) {
      return {
        ok: false,
        error: res.error,
        analysis: res.analysis as OfflineAnalysisDocument | undefined,
      };
    }
    return {
      ok: false,
      error: { code: "analysis_failed", message: "Unexpected analyze response" },
    };
  } catch {
    return {
      ok: false,
      error: {
        code: "backend_unavailable",
        message: "Could not reach the extension service worker / local API",
      },
    };
  }
}
