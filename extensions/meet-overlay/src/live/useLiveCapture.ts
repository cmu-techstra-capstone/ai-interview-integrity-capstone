import { useCallback, useEffect, useState } from "react";
import {
  CaptureStatus,
  initialCaptureSnapshot,
  type CaptureSnapshot,
} from "../types/capture";
import { MessageType, type ExtensionMessage } from "../types/messages";
import {
  bridgeCaptureStart,
  bridgeCaptureStatus,
  bridgeCaptureStop,
} from "./captureBridge";

export function useLiveCapture() {
  const [consentConfirmed, setConsentConfirmed] = useState(false);
  const [snapshot, setSnapshot] = useState<CaptureSnapshot>(initialCaptureSnapshot);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const next = await bridgeCaptureStatus();
    setSnapshot(next);
  }, []);

  useEffect(() => {
    void refresh();

    const onMessage = (message: ExtensionMessage) => {
      if (message?.type === MessageType.CAPTURE_STATUS_EVENT) {
        setSnapshot(message.snapshot);
        if (
          message.snapshot.status === CaptureStatus.ERROR ||
          message.snapshot.status === CaptureStatus.PERMISSION_DENIED
        ) {
          setErrorMessage(message.snapshot.message);
        }
      }
    };
    chrome.runtime.onMessage.addListener(onMessage);
    return () => {
      chrome.runtime.onMessage.removeListener(onMessage);
    };
  }, [refresh]);

  const start = useCallback(async () => {
    setBusy(true);
    setErrorMessage(null);
    const result = await bridgeCaptureStart(consentConfirmed);
    setSnapshot(result.snapshot);
    if (!result.ok) {
      setErrorMessage(result.errorMessage);
    }
    setBusy(false);
  }, [consentConfirmed]);

  const stop = useCallback(async () => {
    setBusy(true);
    setErrorMessage(null);
    const result = await bridgeCaptureStop();
    setSnapshot(result.snapshot);
    if (!result.ok) {
      setErrorMessage(result.errorMessage);
    }
    setBusy(false);
  }, []);

  const resetLocal = useCallback(() => {
    setConsentConfirmed(false);
    setErrorMessage(null);
    setSnapshot(initialCaptureSnapshot());
  }, []);

  return {
    consentConfirmed,
    setConsentConfirmed,
    snapshot,
    errorMessage,
    busy,
    start,
    stop,
    refresh,
    resetLocal,
  };
}
