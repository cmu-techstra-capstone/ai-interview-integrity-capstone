/** Messages between the service worker and the Meet content script (Phase 1). */

export const HOST_ELEMENT_ID = "interview-integrity-overlay-host";

export const MessageType = {
  OPEN_OVERLAY: "II_OPEN_OVERLAY",
  PING: "II_PING",
  PONG: "II_PONG",
} as const;

export type ExtensionMessage =
  | { type: typeof MessageType.OPEN_OVERLAY }
  | { type: typeof MessageType.PING }
  | { type: typeof MessageType.PONG };
