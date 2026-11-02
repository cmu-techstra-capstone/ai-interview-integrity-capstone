/**
 * Local-only overlay harness — no Google Meet tab required.
 * Open via toolbar (off Meet) or chrome-extension://<id>/harness.html
 */

import { mountOverlay } from "../content/mount";

declare global {
  interface Window {
    __interviewIntegrityLocalHarness__?: boolean;
  }
}

function boot(): void {
  if (window.__interviewIntegrityLocalHarness__) return;
  window.__interviewIntegrityLocalHarness__ = true;
  mountOverlay({ startOpen: true });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot, { once: true });
} else {
  boot();
}
