/**
 * MV3 service worker: toolbar action, localhost API proxy, live tab-audio coordination.
 */

import { LocalApiClient } from "../api/client";
import { DEFAULT_API_CONFIG, isSafeRelativePath } from "../api/config";
import {
  beginStart,
  createCaptureSession,
  isCaptureActive,
  markBackendDisconnected,
  markCapturing,
  markError,
  markFromLivePayload,
  markInterrupted,
  markPermissionDenied,
  markStopped,
  markTransmitting,
  type CaptureSession,
} from "./captureSession";
import {
  MessageType,
  type AnalyzeOfflineMessagePayload,
  type ExtensionMessage,
  type ExtensionResponse,
  type OffscreenChunkPayload,
} from "../types/messages";
import type { CaptureSnapshot } from "../types/capture";

const MEET_ORIGIN = "https://meet.google.com/";
const OFFSCREEN_PATH = "offscreen.html";
const OFFSCREEN_REASON_JUSTIFICATION =
  "Hold authorized Google Meet tab audio MediaStream, keep meeting playback audible, and produce bounded PCM chunks for localhost analysis.";

let captureSession: CaptureSession = createCaptureSession();
let creatingOffscreen: Promise<void> | null = null;
let inflightChunk: Promise<void> | null = null;
let stopRequested = false;

/** On SW start / extension reload, tear down any leftover offscreen capture document. */
void (async () => {
  try {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT],
    });
    if (contexts.some((ctx) => ctx.documentUrl?.endsWith(`/${OFFSCREEN_PATH}`))) {
      try {
        await chrome.runtime.sendMessage({ type: MessageType.OFFSCREEN_STOP });
      } catch {
        /* ignore */
      }
      try {
        await chrome.offscreen.closeDocument();
      } catch {
        /* ignore */
      }
    }
  } catch {
    /* getContexts / offscreen may be unavailable during early boot */
  }
  captureSession = createCaptureSession();
  stopRequested = false;
  inflightChunk = null;
})();

function isMeetUrl(url: string | undefined): boolean {
  return typeof url === "string" && url.startsWith(MEET_ORIGIN);
}

function isLocalHarnessUrl(url: string | undefined): boolean {
  if (typeof url !== "string") return false;
  try {
    const u = new URL(url);
    return (
      u.protocol === "chrome-extension:" &&
      u.hostname === chrome.runtime.id &&
      (u.pathname === "/harness.html" || u.pathname.endsWith("/harness.html"))
    );
  } catch {
    return false;
  }
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

function snapshotResponse(snapshot: CaptureSnapshot): ExtensionResponse {
  return { ok: true, kind: "capture", snapshot };
}

async function broadcastCaptureStatus(snapshot: CaptureSnapshot): Promise<void> {
  const tabId = snapshot.tabId;
  if (tabId == null) return;
  try {
    await chrome.tabs.sendMessage(tabId, {
      type: MessageType.CAPTURE_STATUS_EVENT,
      snapshot,
    } satisfies ExtensionMessage);
  } catch {
    /* content script may be gone */
  }
}

function setSession(next: CaptureSession): CaptureSession {
  captureSession = next;
  void broadcastCaptureStatus(next.snapshot);
  return next;
}

async function hasOffscreenDocument(): Promise<boolean> {
  const contexts = await chrome.runtime.getContexts({
    contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT],
  });
  return contexts.some((ctx) => ctx.documentUrl?.endsWith(`/${OFFSCREEN_PATH}`));
}

function getTabMediaStreamId(tabId: number): Promise<string> {
  return new Promise((resolve, reject) => {
    try {
      chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }, (streamId) => {
        const err = chrome.runtime.lastError;
        if (err) {
          reject(new Error(err.message));
          return;
        }
        if (!streamId) {
          reject(new Error("tabCapture returned an empty stream id"));
          return;
        }
        resolve(streamId);
      });
    } catch (err) {
      reject(err instanceof Error ? err : new Error(String(err)));
    }
  });
}

async function ensureOffscreenDocument(): Promise<void> {
  if (await hasOffscreenDocument()) return;
  if (creatingOffscreen) {
    await creatingOffscreen;
    return;
  }
  creatingOffscreen = (async () => {
    await chrome.offscreen.createDocument({
      url: OFFSCREEN_PATH,
      reasons: [
        chrome.offscreen.Reason.USER_MEDIA,
        chrome.offscreen.Reason.AUDIO_PLAYBACK,
      ],
      justification: OFFSCREEN_REASON_JUSTIFICATION,
    });
  })();
  try {
    await creatingOffscreen;
  } finally {
    creatingOffscreen = null;
  }
}

async function closeOffscreenDocument(): Promise<void> {
  if (!(await hasOffscreenDocument())) return;
  try {
    await chrome.offscreen.closeDocument();
  } catch {
    /* already closed */
  }
}

async function stopCaptureInternal(detail?: string): Promise<CaptureSnapshot> {
  stopRequested = true;
  const sessionId = captureSession.snapshot.sessionId;

  try {
    if (await hasOffscreenDocument()) {
      await chrome.runtime.sendMessage({ type: MessageType.OFFSCREEN_STOP } satisfies ExtensionMessage);
      await delay(80);
    }
  } catch {
    /* offscreen may already be gone */
  }
  await closeOffscreenDocument();

  let live = captureSession.snapshot.live;
  if (sessionId) {
    try {
      const config = await loadApiConfig();
      const client = new LocalApiClient(config);
      const result = await client.liveStop(sessionId);
      if (result.ok) live = result.live;
    } catch {
      /* best-effort */
    }
  }

  const next = markStopped(captureSession, detail, live);
  setSession(next);
  stopRequested = false;
  return next.snapshot;
}

async function startCaptureForTab(
  tabId: number,
  tabUrl: string | undefined,
  consentConfirmed: boolean,
  stt?: string,
): Promise<ExtensionResponse> {
  if (!consentConfirmed) {
    return {
      ok: false,
      error: {
        code: "consent_required",
        message: "Confirm participant consent before starting live audio capture.",
      },
      snapshot: captureSession.snapshot,
    };
  }

  if (!isMeetUrl(tabUrl)) {
    return {
      ok: false,
      error: {
        code: "not_meet_tab",
        message: "Live audio capture only works on an active Google Meet tab.",
      },
      snapshot: captureSession.snapshot,
    };
  }

  const started = beginStart(captureSession, tabId);
  if (!started.ok) {
    return {
      ok: false,
      error: { code: "duplicate_session", message: started.reason },
      snapshot: started.session.snapshot,
    };
  }
  setSession(started.session);
  stopRequested = false;

  try {
    const config = await loadApiConfig();
    const client = new LocalApiClient(config);
    const health = await client.health();
    if (!health.ok) {
      const next = markBackendDisconnected(
        captureSession,
        health.error.message || "Local FastAPI health check failed",
      );
      setSession(next);
      return {
        ok: false,
        error: { code: "backend_unavailable", message: health.error.message },
        snapshot: next.snapshot,
      };
    }

    const liveStart = await client.liveStart({
      consentConfirmed: true,
      meetTabConfirmed: true,
      stt,
    });
    if (!liveStart.ok) {
      const next = markError(captureSession, liveStart.error.message);
      setSession(next);
      return {
        ok: false,
        error: liveStart.error,
        snapshot: next.snapshot,
      };
    }

    await ensureOffscreenDocument();
    const streamId = await getTabMediaStreamId(tabId);
    await chrome.runtime.sendMessage({
      type: MessageType.OFFSCREEN_START,
      streamId,
      tabId,
    } satisfies ExtensionMessage);

    setSession(
      markCapturing(captureSession, {
        sessionId: liveStart.live.session_id,
        live: liveStart.live,
      }),
    );
    return snapshotResponse(captureSession.snapshot);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Could not start tab audio capture";
    const denied = /permission|denied|not allowed|activeTab|gesture/i.test(message);
    const next = denied
      ? markPermissionDenied(captureSession, message)
      : markError(captureSession, message);
    setSession(next);
    await closeOffscreenDocument();
    return {
      ok: false,
      error: {
        code: denied ? "permission_denied" : "capture_failed",
        message,
      },
      snapshot: next.snapshot,
    };
  }
}

async function handleOffscreenChunk(payload: OffscreenChunkPayload): Promise<void> {
  if (stopRequested) return;
  if (!isCaptureActive(captureSession)) return;
  if (captureSession.snapshot.tabId !== payload.tabId) return;
  const sessionId = captureSession.snapshot.sessionId;
  if (!sessionId) return;

  // Serialize chunk uploads to preserve sequence order and avoid duplicate in-flight posts.
  const run = async () => {
    setSession(markTransmitting(captureSession));
    const config = await loadApiConfig();
    const client = new LocalApiClient(config);
    const result = await client.liveChunk(sessionId, {
      sequence: payload.sequence,
      sampleRate: payload.sampleRate,
      channels: payload.channels,
      encoding: "pcm_s16le",
      pcmBase64: payload.pcmBase64,
      durationMs: payload.durationMs,
      clientRelStartMs: payload.clientRelStartMs,
    });
    if (stopRequested) return;
    if (!result.ok) {
      if (result.error.code === "backend_unavailable") {
        setSession(markBackendDisconnected(captureSession, result.error.message));
        await stopCaptureInternal(result.error.message);
        return;
      }
      setSession(markError(captureSession, result.error.message));
      return;
    }
    setSession(
      markFromLivePayload(
        {
          snapshot: {
            ...captureSession.snapshot,
            sequence: payload.sequence,
          },
        },
        result.live,
      ),
    );
  };

  inflightChunk = (inflightChunk ?? Promise.resolve()).then(run, run).finally(() => {
    /* keep chain */
  });
  await inflightChunk;
}

chrome.action.onClicked.addListener((tab) => {
  void (async () => {
    if (tab.id != null && isLocalHarnessUrl(tab.url)) {
      try {
        await chrome.tabs.reload(tab.id);
      } catch (err) {
        console.warn("[Interview Integrity] Could not refresh local harness tab.", err);
      }
      return;
    }

    if (tab.id != null && isMeetUrl(tab.url)) {
      try {
        await openOverlayOnTab(tab.id);
      } catch (err) {
        console.warn(
          "[Interview Integrity] Overlay unavailable. Wait for the Meet page to finish loading, then try again.",
          err,
        );
      }
      return;
    }

    try {
      await chrome.tabs.create({ url: chrome.runtime.getURL("harness.html") });
    } catch (err) {
      console.warn("[Interview Integrity] Could not open local harness page.", err);
    }
  })();
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (captureSession.snapshot.tabId === tabId && isCaptureActive(captureSession)) {
    void (async () => {
      await stopCaptureInternal("Capture stopped because the Google Meet tab closed.");
      setSession(
        markInterrupted(
          captureSession,
          "Capture stopped because the Google Meet tab closed.",
        ),
      );
    })();
  }
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

chrome.runtime.onMessage.addListener((message: ExtensionMessage, sender, sendResponse) => {
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
    return true;
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

  if (message.type === MessageType.CAPTURE_STATUS) {
    sendResponse(snapshotResponse(captureSession.snapshot));
    return false;
  }

  if (message.type === MessageType.CAPTURE_STOP) {
    void (async () => {
      const snapshot = await stopCaptureInternal(
        "Live audio capture stopped. Audio was not recorded to disk or sent externally.",
      );
      sendResponse(snapshotResponse(snapshot));
    })();
    return true;
  }

  if (message.type === MessageType.CAPTURE_START) {
    void (async () => {
      const tabId = sender.tab?.id;
      if (tabId == null) {
        sendResponse({
          ok: false,
          error: {
            code: "no_tab",
            message: "Capture must be started from the Google Meet overlay.",
          },
          snapshot: captureSession.snapshot,
        });
        return;
      }
      const result = await startCaptureForTab(
        tabId,
        sender.tab?.url,
        Boolean(message.payload?.consentConfirmed),
        message.payload?.stt,
      );
      sendResponse(result);
    })();
    return true;
  }

  if (message.type === MessageType.OFFSCREEN_CHUNK) {
    void handleOffscreenChunk(message.payload);
    return false;
  }

  if (message.type === MessageType.OFFSCREEN_STARTED) {
    if (captureSession.snapshot.tabId === message.tabId) {
      setSession(
        markCapturing(captureSession, {
          sessionId: captureSession.snapshot.sessionId,
          live: captureSession.snapshot.live,
        }),
      );
    }
    return false;
  }

  if (message.type === MessageType.OFFSCREEN_FAILED) {
    if (captureSession.snapshot.tabId === message.tabId) {
      const next =
        message.code === "permission_denied"
          ? markPermissionDenied(captureSession, message.message)
          : markError(captureSession, message.message);
      setSession(next);
      void (async () => {
        const sessionId = captureSession.snapshot.sessionId;
        if (sessionId) {
          try {
            const config = await loadApiConfig();
            await new LocalApiClient(config).liveStop(sessionId);
          } catch {
            /* ignore */
          }
        }
        await closeOffscreenDocument();
      })();
    }
    return false;
  }

  if (message.type === MessageType.OFFSCREEN_ENDED) {
    if (captureSession.snapshot.tabId === message.tabId) {
      void (async () => {
        if (message.reason === "interrupted") {
          await stopCaptureInternal(message.message);
          setSession(markInterrupted(captureSession, message.message));
        }
      })();
    }
    return false;
  }

  return false;
});
