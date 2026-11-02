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

  it("content sources do not call capture APIs or backend fetch", () => {
    const main = readFileSync(join(here, "main.tsx"), "utf8");
    const mount = readFileSync(join(here, "mount.tsx"), "utf8");
    const overlay = readFileSync(join(here, "../components/OverlayApp.tsx"), "utf8");
    const src = main + mount + overlay;
    for (const needle of ["getUserMedia", "tabCapture", "desktopCapture", "WebSocket", "EventSource"]) {
      expect(src.includes(needle)).toBe(false);
    }
  });
});
