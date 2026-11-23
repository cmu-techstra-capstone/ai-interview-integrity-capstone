import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { HOST_ELEMENT_ID } from "../types/messages";

const here = dirname(fileURLToPath(import.meta.url));

describe("overlay guards", () => {
  it("uses a stable host id to prevent duplicate overlays", () => {
    expect(HOST_ELEMENT_ID).toBe("interview-integrity-overlay-host");
  });

  it("content/UI sources do not redeem MediaStreams or open arbitrary network sockets", () => {
    const main = readFileSync(join(here, "main.tsx"), "utf8");
    const mount = readFileSync(join(here, "mount.tsx"), "utf8");
    const overlay = readFileSync(join(here, "../components/OverlayApp.tsx"), "utf8");
    const liveControls = readFileSync(join(here, "../components/LiveCaptureControls.tsx"), "utf8");
    const captureBridge = readFileSync(join(here, "../live/captureBridge.ts"), "utf8");
    const adapter = readFileSync(join(here, "../adapters/mapAnalysisContract.ts"), "utf8");
    const offlinePanel = readFileSync(join(here, "../panel/OfflineAnalysisPanel.tsx"), "utf8");
    const bridge = readFileSync(join(here, "../api/bridge.ts"), "utf8");
    const src =
      main + mount + overlay + liveControls + captureBridge + adapter + offlinePanel + bridge;
    for (const needle of [
      "getUserMedia",
      "tabCapture",
      "desktopCapture",
      "WebSocket",
      "EventSource",
      "MediaRecorder",
    ]) {
      expect(src.includes(needle)).toBe(false);
    }
    // Content/UI path talks to the service worker only — no direct page fetch.
    expect(bridge.includes("chrome.runtime.sendMessage")).toBe(true);
    expect(captureBridge.includes("chrome.runtime.sendMessage")).toBe(true);
  });

  it("manifest enables Meet tabCapture + offscreen only (no desktopCapture / all_urls)", () => {
    const copyStatic = readFileSync(join(here, "../../scripts/copy-static.mjs"), "utf8");
    expect(copyStatic.includes("https://meet.google.com/*")).toBe(true);
    expect(copyStatic.includes("http://127.0.0.1:8765/*")).toBe(true);
    expect(copyStatic.includes("http://localhost:8765/*")).toBe(true);
    expect(copyStatic.includes('"tabCapture"')).toBe(true);
    expect(copyStatic.includes('"offscreen"')).toBe(true);
    expect(copyStatic.includes("desktopCapture")).toBe(false);
    expect(copyStatic.includes("<all_urls>")).toBe(false);
  });

  it("offscreen capture module is audio-only, chunks PCM, and does not persist by default", () => {
    const offscreen = readFileSync(join(here, "../background/offscreen.ts"), "utf8");
    expect(offscreen.includes("getUserMedia")).toBe(true);
    expect(offscreen.includes('chromeMediaSource: "tab"')).toBe(true);
    expect(offscreen.includes("video: false")).toBe(true);
    expect(offscreen.includes("MediaRecorder")).toBe(false);
    expect(offscreen.includes("createMediaStreamSource")).toBe(true);
    expect(offscreen.includes("audioContext.destination")).toBe(true);
    expect(offscreen.includes("encodePcmChunkBase64")).toBe(true);
    expect(offscreen.includes("OFFSCREEN_CHUNK") || offscreen.includes("MessageType.OFFSCREEN_CHUNK")).toBe(
      true,
    );
  });

  it("service worker coordinates getMediaStreamId, live API, and rejects capture without consent", () => {
    const sw = readFileSync(join(here, "../background/service-worker.ts"), "utf8");
    expect(sw.includes("getMediaStreamId") || sw.includes("getTabMediaStreamId")).toBe(true);
    expect(sw.includes("consentConfirmed")).toBe(true);
    expect(sw.includes("duplicate_session")).toBe(true);
    expect(sw.includes("liveStart")).toBe(true);
    expect(sw.includes("liveChunk")).toBe(true);
    expect(sw.includes("mediaDevices.getUserMedia")).toBe(false);
  });
});
