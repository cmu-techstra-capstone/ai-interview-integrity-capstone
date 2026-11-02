/** Messages between the service worker and the Meet content script. */

export const HOST_ELEMENT_ID = "interview-integrity-overlay-host";

export const MessageType = {
  OPEN_OVERLAY: "II_OPEN_OVERLAY",
  PING: "II_PING",
  PONG: "II_PONG",
  API_HEALTH: "II_API_HEALTH",
  API_ANALYZE: "II_API_ANALYZE",
} as const;

export type AnalyzeOfflineMessagePayload = {
  recordingRelpath: string;
  metadataRelpath: string;
  transcriptRelpath?: string;
  stt?: string;
};

export type ExtensionMessage =
  | { type: typeof MessageType.OPEN_OVERLAY }
  | { type: typeof MessageType.PING }
  | { type: typeof MessageType.PONG }
  | { type: typeof MessageType.API_HEALTH }
  | { type: typeof MessageType.API_ANALYZE; payload: AnalyzeOfflineMessagePayload };

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
      ok: false;
      error: { code: string; message: string };
      analysis?: unknown;
    };
