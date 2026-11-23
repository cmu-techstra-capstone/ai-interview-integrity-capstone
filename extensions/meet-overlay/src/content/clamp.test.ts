import { beforeEach, describe, expect, it } from "vitest";
import { clampPosition, defaultLauncherPosition } from "./clamp";

beforeEach(() => {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: { innerWidth: 1280, innerHeight: 800 },
  });
});

describe("clampPosition", () => {
  it("keeps the overlay inside the viewport", () => {
    const clamped = clampPosition(-40, 9999, 360, 200, 8);
    expect(clamped.x).toBe(8);
    expect(clamped.y).toBe(800 - 200 - 8);
  });

  it("default launcher stays in the lower-right region", () => {
    const pos = defaultLauncherPosition(56);
    expect(pos.x).toBeGreaterThan(1280 / 2);
    expect(pos.y).toBeGreaterThan(0);
    expect(pos.x + 56).toBeLessThanOrEqual(1280 - 8);
  });
});
