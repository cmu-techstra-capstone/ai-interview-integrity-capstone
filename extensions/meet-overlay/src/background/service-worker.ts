/**
 * MV3 service worker: toolbar action + allowlisted localhost API proxy.
 * No media capture. Does not accept arbitrary URLs or absolute filesystem paths.
 */

import { LocalApiClient } from "../api/client";
import { DEFAULT_API_CONFIG, isSafeRelativePath } from "../api/config";
import {
  MessageType,
  type AnalyzeOfflineMessagePayload,
  type ExtensionMessage,
} from "../types/messages";

const MEET_ORIGIN = "https://meet.google.com/";

function isMeetUrl(url: string | undefined): boolean {
  return typeof url === "string" && url.startsWith(MEET_ORIGIN);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function loadApiConfig(): Promise<typeof DEFAULT_API_CONFIG> {
  try {
    const url = chrome.runtime.getURL("api-config.json");
    const res = await fetch(url);
    if (!res.ok) return DEFAULT_API_CONFIG;
    const data = (await res.json()) as Partial<typeof DEFAULT_API_CONFIG>;
    return {
      apiBaseUrl: data.apiBaseUrl || DEFAULT_API_CONFIG.apiBaseUrl,
      allowedHosts: data.allowedHosts || DEFAULT_API_CONFIG.allowedHosts,
    };
  } catch {
    return DEFAULT_API_CONFIG;
  }
}

async function openOverlayOnTab(tabId: number): Promise<void> {
  const message = { type: MessageType.OPEN_OVERLAY };
  try {
    await chrome.tabs.sendMessage(tabId, message);
  } catch {
    await delay(150);
    await chrome.tabs.sendMessage(tabId, message);
  }
}

chrome.action.onClicked.addListener((tab) => {
  void (async () => {
    if (tab.id == null || !isMeetUrl(tab.url)) {
      return;
    }
    try {
      await openOverlayOnTab(tab.id);
    } catch (err) {
      console.warn(
        "[Interview Integrity] Overlay unavailable. Wait for the Meet page to finish loading, then try again.",
        err,
      );
    }
  })();
});

function validateAnalyzePayload(payload: AnalyzeOfflineMessagePayload | undefined): string | null {
  if (!payload || typeof payload !== "object") return "Missing analyze payload";
  if (!isSafeRelativePath(payload.recordingRelpath || "")) {
    return "recordingRelpath must be a relative path without '..'";
  }
  if (!isSafeRelativePath(payload.metadataRelpath || "")) {
    return "metadataRelpath must be a relative path without '..'";
  }
  if (payload.transcriptRelpath && !isSafeRelativePath(payload.transcriptRelpath)) {
    return "transcriptRelpath must be a relative path without '..'";
  }
  return null;
}

chrome.runtime.onMessage.addListener((message: ExtensionMessage, _sender, sendResponse) => {
  if (!message || typeof message !== "object" || !("type" in message)) {
    return false;
  }

  if (message.type === MessageType.API_HEALTH) {
    void (async () => {
      try {
        const config = await loadApiConfig();
        const client = new LocalApiClient(config);
        const result = await client.health();
        if (result.ok) {
          sendResponse({
            ok: true,
            kind: "health",
            detectionModel: result.detectionModel,
            recordingsDirConfigured: result.recordingsDirConfigured,
          });
        } else {
          sendResponse({ ok: false, error: result.error });
        }
      } catch (err) {
        sendResponse({
          ok: false,
          error: {
            code: "backend_unavailable",
            message: err instanceof Error ? err.message : "Local API unavailable",
          },
        });
      }
    })();
    return true; // async
  }

  if (message.type === MessageType.API_ANALYZE) {
    void (async () => {
      const invalid = validateAnalyzePayload(message.payload);
      if (invalid) {
        sendResponse({
          ok: false,
          error: { code: "validation_error", message: invalid },
        });
        return;
      }
      try {
        const config = await loadApiConfig();
        const client = new LocalApiClient(config);
        const result = await client.analyzeOffline(message.payload);
        if (result.ok) {
          sendResponse({ ok: true, kind: "analyze", analysis: result.analysis });
        } else {
          sendResponse({
            ok: false,
            error: result.error,
            analysis: result.analysis,
          });
        }
      } catch (err) {
        sendResponse({
          ok: false,
          error: {
            code: "analysis_failed",
            message: err instanceof Error ? err.message : "Analysis request failed",
          },
        });
      }
    })();
    return true;
  }

  return false;
});
