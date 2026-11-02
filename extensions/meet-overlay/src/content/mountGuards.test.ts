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

  it("content sources do not call capture APIs or open arbitrary network sockets", () => {
    const main = readFileSync(join(here, "main.tsx"), "utf8");
    const mount = readFileSync(join(here, "mount.tsx"), "utf8");
    const overlay = readFileSync(join(here, "../components/OverlayApp.tsx"), "utf8");
    const adapter = readFileSync(join(here, "../adapters/mapAnalysisContract.ts"), "utf8");
    const offlinePanel = readFileSync(join(here, "../panel/OfflineAnalysisPanel.tsx"), "utf8");
    const bridge = readFileSync(join(here, "../api/bridge.ts"), "utf8");
    const src = main + mount + overlay + adapter + offlinePanel + bridge;
    for (const needle of [
      "getUserMedia",
      "tabCapture",
      "desktopCapture",
      "WebSocket",
      "EventSource",
    ]) {
      expect(src.includes(needle)).toBe(false);
    }
    // Content/UI path talks to the service worker only — no direct page fetch.
    expect(bridge.includes("chrome.runtime.sendMessage")).toBe(true);
    expect(overlay.includes("getUserMedia")).toBe(false);
  });

  it("manifest host permissions stay narrow (Meet + loopback API)", () => {
    // Source of truth is the copy-static generator (dist may be absent in unit runs).
    const copyStatic = readFileSync(join(here, "../../scripts/copy-static.mjs"), "utf8");
    expect(copyStatic.includes("https://meet.google.com/*")).toBe(true);
    expect(copyStatic.includes("http://127.0.0.1:8765/*")).toBe(true);
    expect(copyStatic.includes("http://localhost:8765/*")).toBe(true);
    expect(copyStatic.includes('"tabCapture"')).toBe(false);
    expect(copyStatic.includes("<all_urls>")).toBe(false);
  });
});
