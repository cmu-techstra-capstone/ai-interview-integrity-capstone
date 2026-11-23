/**
 * Live Meet tab-audio capture + transport UI/state contract.
 */

import type { LiveSessionPayload } from "./liveApi";

export const CaptureStatus = {
  STOPPED: "stopped",
  STARTING: "starting",
  CAPTURING: "capturing",
  TRANSMITTING: "transmitting",
  TRANSCRIBING: "transcribing",
  BACKEND_DISCONNECTED: "backend_disconnected",
  STT_UNAVAILABLE: "stt_unavailable",
  PERMISSION_DENIED: "permission_denied",
  INTERRUPTED: "interrupted",
  ERROR: "error",
} as const;

export type CaptureStatus = (typeof CaptureStatus)[keyof typeof CaptureStatus];

export type CaptureSnapshot = {
  status: CaptureStatus;
  tabId: number | null;
  message: string | null;
  startedAt: number | null;
  /** True only while an active MediaStream is held in the offscreen document. */
  hasActiveStream: boolean;
  sessionId: string | null;
  sequence: number;
  live: LiveSessionPayload | null;
  backendConnected: boolean | null;
};

export function initialCaptureSnapshot(): CaptureSnapshot {
  return {
    status: CaptureStatus.STOPPED,
    tabId: null,
    message: null,
    startedAt: null,
    hasActiveStream: false,
    sessionId: null,
    sequence: 0,
    live: null,
    backendConnected: null,
  };
}

export function captureStatusLabel(status: CaptureStatus): string {
  switch (status) {
    case CaptureStatus.STOPPED:
      return "Stopped";
    case CaptureStatus.STARTING:
      return "Starting…";
    case CaptureStatus.CAPTURING:
      return "Capturing audio";
    case CaptureStatus.TRANSMITTING:
      return "Transmitting audio";
    case CaptureStatus.TRANSCRIBING:
      return "Transcribing";
    case CaptureStatus.BACKEND_DISCONNECTED:
      return "Backend disconnected";
    case CaptureStatus.STT_UNAVAILABLE:
      return "STT unavailable";
    case CaptureStatus.PERMISSION_DENIED:
      return "Permission denied";
    case CaptureStatus.INTERRUPTED:
      return "Interrupted";
    case CaptureStatus.ERROR:
      return "Error";
    default:
      return status;
  }
}
