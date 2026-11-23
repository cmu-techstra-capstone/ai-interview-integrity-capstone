import { describe, expect, it } from "vitest";
import {
  CaptureStatus,
  captureStatusLabel,
  initialCaptureSnapshot,
} from "./capture";

describe("capture status labels", () => {
  it("covers every capture status used by the UI", () => {
    expect(captureStatusLabel(CaptureStatus.STOPPED)).toBe("Stopped");
    expect(captureStatusLabel(CaptureStatus.STARTING)).toBe("Starting…");
    expect(captureStatusLabel(CaptureStatus.CAPTURING)).toBe("Capturing audio");
    expect(captureStatusLabel(CaptureStatus.TRANSMITTING)).toBe("Transmitting audio");
    expect(captureStatusLabel(CaptureStatus.TRANSCRIBING)).toBe("Transcribing");
    expect(captureStatusLabel(CaptureStatus.BACKEND_DISCONNECTED)).toBe("Backend disconnected");
    expect(captureStatusLabel(CaptureStatus.STT_UNAVAILABLE)).toBe("STT unavailable");
    expect(captureStatusLabel(CaptureStatus.PERMISSION_DENIED)).toBe("Permission denied");
    expect(captureStatusLabel(CaptureStatus.INTERRUPTED)).toBe("Interrupted");
    expect(captureStatusLabel(CaptureStatus.ERROR)).toBe("Error");
  });

  it("initial snapshot is stopped with no stream", () => {
    const snap = initialCaptureSnapshot();
    expect(snap.status).toBe(CaptureStatus.STOPPED);
    expect(snap.hasActiveStream).toBe(false);
    expect(snap.tabId).toBeNull();
    expect(snap.sessionId).toBeNull();
    expect(snap.live).toBeNull();
  });
});
