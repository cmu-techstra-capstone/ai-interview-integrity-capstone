/**
 * Content-script bridge for live tab-audio capture (service worker only).
 * Page context never redeems media streams; capture APIs stay in SW/offscreen.
 */

import type { CaptureSnapshot } from "../types/capture";
import { initialCaptureSnapshot } from "../types/capture";
import { MessageType, type ExtensionResponse } from "../types/messages";

function send<T extends ExtensionResponse>(message: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendMessage(message, (response) => {
        const err = chrome.runtime.lastError;
        if (err) {
          reject(new Error(err.message));
          return;
        }
        resolve(response as T);
      });
    } catch (err) {
      reject(err);
    }
  });
}

function asCaptureResult(res: ExtensionResponse): {
  ok: boolean;
  snapshot: CaptureSnapshot;
  errorMessage: string | null;
} {
  if (res && "ok" in res && res.ok && "kind" in res && res.kind === "capture") {
    return { ok: true, snapshot: res.snapshot, errorMessage: null };
  }
  if (res && "ok" in res && res.ok === false) {
    return {
      ok: false,
      snapshot: res.snapshot ?? initialCaptureSnapshot(),
      errorMessage: res.error.message,
    };
  }
  return {
    ok: false,
    snapshot: initialCaptureSnapshot(),
    errorMessage: "Unexpected capture response",
  };
}

export async function bridgeCaptureStart(consentConfirmed: boolean): Promise<{
  ok: boolean;
  snapshot: CaptureSnapshot;
  errorMessage: string | null;
}> {
  try {
    const res = await send<ExtensionResponse>({
      type: MessageType.CAPTURE_START,
      payload: { consentConfirmed },
    });
    return asCaptureResult(res);
  } catch (err) {
    return {
      ok: false,
      snapshot: initialCaptureSnapshot(),
      errorMessage: err instanceof Error ? err.message : "Could not start capture",
    };
  }
}

export async function bridgeCaptureStop(): Promise<{
  ok: boolean;
  snapshot: CaptureSnapshot;
  errorMessage: string | null;
}> {
  try {
    const res = await send<ExtensionResponse>({ type: MessageType.CAPTURE_STOP });
    return asCaptureResult(res);
  } catch (err) {
    return {
      ok: false,
      snapshot: initialCaptureSnapshot(),
      errorMessage: err instanceof Error ? err.message : "Could not stop capture",
    };
  }
}

export async function bridgeCaptureStatus(): Promise<CaptureSnapshot> {
  try {
    const res = await send<ExtensionResponse>({ type: MessageType.CAPTURE_STATUS });
    return asCaptureResult(res).snapshot;
  } catch {
    return initialCaptureSnapshot();
  }
}
