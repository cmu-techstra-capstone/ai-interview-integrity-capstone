/**
 * Content script for https://meet.google.com/*
 * Stays dormant until the toolbar asks to open the overlay.
 * Does not scrape Meet DOM content (participants, captions, chat).
 */

import { MessageType, type ExtensionMessage } from "../types/messages";
import { isOverlayMounted, mountOverlay, unmountOverlay } from "./mount";

declare global {
  interface Window {
    __interviewIntegrityMeetOverlay__?: boolean;
  }
}

function onMessage(
  message: ExtensionMessage,
  _sender: chrome.runtime.MessageSender,
  sendResponse: (response?: unknown) => void,
): boolean {
  if (!message || typeof message !== "object" || !("type" in message)) {
    return false;
  }

  if (message.type === MessageType.PING) {
    sendResponse({ type: MessageType.PONG });
    return false;
  }

  if (message.type === MessageType.OPEN_OVERLAY) {
    if (!isOverlayMounted()) {
      mountOverlay();
    }
    sendResponse({ ok: true, mounted: true });
    return false;
  }

  return false;
}

function bootstrap(): void {
  if (window.__interviewIntegrityMeetOverlay__) {
    return;
  }
  window.__interviewIntegrityMeetOverlay__ = true;

  chrome.runtime.onMessage.addListener(onMessage);

  window.addEventListener(
    "pagehide",
    () => {
      unmountOverlay();
    },
    { once: false },
  );
}

bootstrap();
