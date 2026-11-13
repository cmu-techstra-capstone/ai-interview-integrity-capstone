import { describe, expect, it } from "vitest";
import { CaptureStatus } from "../types/capture";
import {
  beginStart,
  createCaptureSession,
  isCaptureActive,
  markCapturing,
  markError,
  markFromLivePayload,
  markInterrupted,
  markPermissionDenied,
  markStopped,
} from "./captureSession";

describe("captureSession state machine", () => {
  it("starts idle/stopped with no active stream", () => {
    const session = createCaptureSession();
    expect(session.snapshot.status).toBe(CaptureStatus.STOPPED);
    expect(session.snapshot.hasActiveStream).toBe(false);
    expect(isCaptureActive(session)).toBe(false);
  });

  it("rejects duplicate start while starting or capturing", () => {
    const base = createCaptureSession();
    const started = beginStart(base, 42);
    expect(started.ok).toBe(true);
    if (!started.ok) return;

    const dupWhileStarting = beginStart(started.session, 99);
    expect(dupWhileStarting.ok).toBe(false);

    const capturing = markCapturing(started.session, { sessionId: "abc" });
    const dupWhileCapturing = beginStart(capturing, 7);
    expect(dupWhileCapturing.ok).toBe(false);
  });

  it("transitions through capturing then stopped", () => {
    const started = beginStart(createCaptureSession(), 5);
    expect(started.ok).toBe(true);
    if (!started.ok) return;

    const capturing = markCapturing(started.session, {
      sessionId: "sess-1",
      startedAt: 1_700_000_000_000,
    });
    expect(capturing.snapshot.status).toBe(CaptureStatus.CAPTURING);
    expect(capturing.snapshot.hasActiveStream).toBe(true);
    expect(capturing.snapshot.sessionId).toBe("sess-1");

    const stopped = markStopped(capturing, "stopped by test");
    expect(stopped.snapshot.status).toBe(CaptureStatus.STOPPED);
    expect(stopped.snapshot.hasActiveStream).toBe(false);
    expect(stopped.snapshot.message).toMatch(/stopped by test/);
  });

  it("maps live STT statuses into UI capture statuses", () => {
    const started = beginStart(createCaptureSession(), 3);
    expect(started.ok).toBe(true);
    if (!started.ok) return;
    const capturing = markCapturing(started.session, { sessionId: "s1" });
    const unavailable = markFromLivePayload(capturing, {
      session_id: "s1",
      status: "active",
      stt_status: "unavailable",
      stt_message: "weights missing",
      transcript_segments: [],
    });
    expect(unavailable.snapshot.status).toBe(CaptureStatus.STT_UNAVAILABLE);
  });

  it("records permission denied, interrupted, and error", () => {
    const started = beginStart(createCaptureSession(), 3);
    expect(started.ok).toBe(true);
    if (!started.ok) return;

    const denied = markPermissionDenied(started.session, "denied");
    expect(denied.snapshot.status).toBe(CaptureStatus.PERMISSION_DENIED);

    const interrupted = markInterrupted(started.session, "tab closed");
    expect(interrupted.snapshot.status).toBe(CaptureStatus.INTERRUPTED);

    const errored = markError(started.session, "boom");
    expect(errored.snapshot.status).toBe(CaptureStatus.ERROR);
    expect(errored.snapshot.message).toBe("boom");
  });
});
