/**
 * Pure capture-session state machine (no Chrome APIs).
 */

import {
  CaptureStatus,
  initialCaptureSnapshot,
  type CaptureSnapshot,
} from "../types/capture";
import type { LiveSessionPayload } from "../types/liveApi";

export type CaptureSession = {
  snapshot: CaptureSnapshot;
};

export function createCaptureSession(): CaptureSession {
  return { snapshot: initialCaptureSnapshot() };
}

export function isCaptureActive(session: CaptureSession): boolean {
  const s = session.snapshot.status;
  return (
    s === CaptureStatus.STARTING ||
    s === CaptureStatus.CAPTURING ||
    s === CaptureStatus.TRANSMITTING ||
    s === CaptureStatus.TRANSCRIBING
  );
}

export function beginStart(
  session: CaptureSession,
  tabId: number,
): { ok: true; session: CaptureSession } | { ok: false; reason: string; session: CaptureSession } {
  if (isCaptureActive(session)) {
    return {
      ok: false,
      reason: "A live audio capture session is already active. Stop it before starting another.",
      session,
    };
  }
  return {
    ok: true,
    session: {
      snapshot: {
        ...initialCaptureSnapshot(),
        status: CaptureStatus.STARTING,
        tabId,
        message: "Requesting tab audio capture and localhost live session…",
        hasActiveStream: false,
        backendConnected: null,
      },
    },
  };
}

export function markCapturing(
  session: CaptureSession,
  opts?: { sessionId?: string | null; startedAt?: number; live?: LiveSessionPayload | null },
): CaptureSession {
  return {
    snapshot: {
      ...session.snapshot,
      status: CaptureStatus.CAPTURING,
      message:
        "Capturing Google Meet tab audio and sending bounded PCM chunks to localhost FastAPI.",
      startedAt: opts?.startedAt ?? Date.now(),
      hasActiveStream: true,
      sessionId: opts?.sessionId ?? session.snapshot.sessionId,
      live: opts?.live ?? session.snapshot.live,
      backendConnected: true,
    },
  };
}

export function markTransmitting(session: CaptureSession, live?: LiveSessionPayload | null): CaptureSession {
  return {
    snapshot: {
      ...session.snapshot,
      status: CaptureStatus.TRANSMITTING,
      message: "Uploading bounded audio chunk to localhost…",
      live: live ?? session.snapshot.live,
      backendConnected: true,
    },
  };
}

export function markFromLivePayload(session: CaptureSession, live: LiveSessionPayload): CaptureSession {
  let status: CaptureSnapshot["status"] = CaptureStatus.CAPTURING;
  let message = session.snapshot.message;
  if (live.stt_status === "transcribing") {
    status = CaptureStatus.TRANSCRIBING;
    message = live.stt_message || "Transcribing accumulated speech window…";
  } else if (live.stt_status === "unavailable") {
    status = CaptureStatus.STT_UNAVAILABLE;
    message = live.stt_message || "STT unavailable on this machine";
  } else if (live.stt_status === "failed") {
    status = CaptureStatus.ERROR;
    message = live.stt_message || "Transcription failed";
  } else {
    status = CaptureStatus.CAPTURING;
    message = live.stt_message || "Capturing and streaming bounded audio chunks";
  }
  return {
    snapshot: {
      ...session.snapshot,
      status,
      message,
      live,
      sessionId: live.session_id || session.snapshot.sessionId,
      backendConnected: true,
      sequence: Math.max(session.snapshot.sequence, (live.next_expected_sequence || 1) - 1),
    },
  };
}

export function markBackendDisconnected(session: CaptureSession, detail?: string): CaptureSession {
  return {
    snapshot: {
      ...session.snapshot,
      status: CaptureStatus.BACKEND_DISCONNECTED,
      message: detail || "Local FastAPI is unreachable. Capture stopped transmitting.",
      backendConnected: false,
    },
  };
}

export function markPermissionDenied(session: CaptureSession, detail?: string): CaptureSession {
  return {
    snapshot: {
      ...initialCaptureSnapshot(),
      status: CaptureStatus.PERMISSION_DENIED,
      tabId: session.snapshot.tabId,
      message:
        detail ||
        "Tab audio permission was denied or unavailable. Capture was not started.",
    },
  };
}

export function markError(session: CaptureSession, detail: string): CaptureSession {
  return {
    snapshot: {
      ...session.snapshot,
      status: CaptureStatus.ERROR,
      message: detail,
      hasActiveStream: false,
    },
  };
}

export function markInterrupted(session: CaptureSession, detail?: string): CaptureSession {
  return {
    snapshot: {
      ...session.snapshot,
      status: CaptureStatus.INTERRUPTED,
      message:
        detail ||
        "Capture stopped because the tab closed or the media stream ended.",
      startedAt: null,
      hasActiveStream: false,
      sessionId: null,
    },
  };
}

export function markStopped(session: CaptureSession, detail?: string, live?: LiveSessionPayload | null): CaptureSession {
  return {
    snapshot: {
      ...initialCaptureSnapshot(),
      status: CaptureStatus.STOPPED,
      message: detail || "Live audio capture stopped. Audio was not saved to disk.",
      live: live ?? null,
      backendConnected: session.snapshot.backendConnected,
    },
  };
}
