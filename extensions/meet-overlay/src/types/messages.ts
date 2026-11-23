/** Messages between the service worker, content script, and offscreen capture document. */

import type { CaptureSnapshot } from "./capture";

export const HOST_ELEMENT_ID = "interview-integrity-overlay-host";

export const MessageType = {
  OPEN_OVERLAY: "II_OPEN_OVERLAY",
  PING: "II_PING",
  PONG: "II_PONG",
  API_HEALTH: "II_API_HEALTH",
  API_ANALYZE: "II_API_ANALYZE",
  CAPTURE_START: "II_CAPTURE_START",
  CAPTURE_STOP: "II_CAPTURE_STOP",
  CAPTURE_STATUS: "II_CAPTURE_STATUS",
  CAPTURE_STATUS_EVENT: "II_CAPTURE_STATUS_EVENT",
  /** Internal: service worker → offscreen document */
  OFFSCREEN_START: "II_OFFSCREEN_START",
  OFFSCREEN_STOP: "II_OFFSCREEN_STOP",
  OFFSCREEN_STARTED: "II_OFFSCREEN_STARTED",
  OFFSCREEN_FAILED: "II_OFFSCREEN_FAILED",
  OFFSCREEN_ENDED: "II_OFFSCREEN_ENDED",
  /** Internal: offscreen → service worker PCM chunk */
  OFFSCREEN_CHUNK: "II_OFFSCREEN_CHUNK",
} as const;

export type AnalyzeOfflineMessagePayload = {
  recordingRelpath: string;
  metadataRelpath: string;
  transcriptRelpath?: string;
  stt?: string;
};

export type CaptureStartPayload = {
  /** Explicit participant-consent confirmation from the interviewer UI. */
  consentConfirmed: boolean;
  /** Optional STT registry override (tests may use fake-live). */
  stt?: string;
};

export type OffscreenChunkPayload = {
  tabId: number;
  sequence: number;
  sampleRate: number;
  channels: number;
  encoding: "pcm_s16le";
  pcmBase64: string;
  durationMs: number;
  clientRelStartMs: number;
};

export type ExtensionMessage =
  | { type: typeof MessageType.OPEN_OVERLAY }
  | { type: typeof MessageType.PING }
  | { type: typeof MessageType.PONG }
  | { type: typeof MessageType.API_HEALTH }
  | { type: typeof MessageType.API_ANALYZE; payload: AnalyzeOfflineMessagePayload }
  | { type: typeof MessageType.CAPTURE_START; payload: CaptureStartPayload }
  | { type: typeof MessageType.CAPTURE_STOP }
  | { type: typeof MessageType.CAPTURE_STATUS }
  | { type: typeof MessageType.CAPTURE_STATUS_EVENT; snapshot: CaptureSnapshot }
  | { type: typeof MessageType.OFFSCREEN_START; streamId: string; tabId: number }
  | { type: typeof MessageType.OFFSCREEN_STOP }
  | {
      type: typeof MessageType.OFFSCREEN_STARTED;
      tabId: number;
    }
  | {
      type: typeof MessageType.OFFSCREEN_FAILED;
      tabId: number;
      code: "permission_denied" | "error";
      message: string;
    }
  | {
      type: typeof MessageType.OFFSCREEN_ENDED;
      tabId: number;
      reason: "interrupted" | "stopped";
      message?: string;
    }
  | { type: typeof MessageType.OFFSCREEN_CHUNK; payload: OffscreenChunkPayload };

export type ExtensionResponse =
  | { type: typeof MessageType.PONG }
  | { ok: true; mounted?: boolean }
  | {
      ok: true;
      kind: "health";
      detectionModel: string;
      recordingsDirConfigured: boolean;
    }
  | {
      ok: true;
      kind: "analyze";
      analysis: unknown;
    }
  | {
      ok: true;
      kind: "capture";
      snapshot: CaptureSnapshot;
    }
  | {
      ok: false;
      error: { code: string; message: string };
      analysis?: unknown;
      snapshot?: CaptureSnapshot;
    };
