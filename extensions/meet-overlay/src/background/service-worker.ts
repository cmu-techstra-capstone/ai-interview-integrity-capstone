/**
 * MV3 service worker: toolbar action opens the floating overlay on Google Meet.
 * No media capture, no backend calls, no storage of interview data.
 *
 * Relies on the manifest content_script for Meet pages (no `scripting` permission).
 */

import { MessageType } from "../types/messages";

const MEET_ORIGIN = "https://meet.google.com/";

function isMeetUrl(url: string | undefined): boolean {
  return typeof url === "string" && url.startsWith(MEET_ORIGIN);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function openOverlayOnTab(tabId: number): Promise<void> {
  const message = { type: MessageType.OPEN_OVERLAY };
  try {
    await chrome.tabs.sendMessage(tabId, message);
  } catch {
    // Content script may still be loading after navigation.
    await delay(150);
    await chrome.tabs.sendMessage(tabId, message);
  }
}

chrome.action.onClicked.addListener((tab) => {
  void (async () => {
    if (tab.id == null || !isMeetUrl(tab.url)) {
      return;
    }
    try {
      await openOverlayOnTab(tab.id);
    } catch (err) {
      console.warn(
        "[Interview Integrity] Overlay unavailable. Wait for the Meet page to finish loading, then try again.",
        err,
      );
    }
  })();
});
