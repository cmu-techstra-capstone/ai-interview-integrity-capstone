import { useCallback, useEffect, useRef, useState } from "react";
import { bridgeAnalyze, bridgeHealth } from "../api/bridge";
import type { AnalyzeOfflineRequestPayload, ConnectionState } from "../api/types";
import type { OfflineAnalysisDocument } from "../types/analysisContract";
import { mapOfflineAnalysisToPanelModel, type OverlayPanelModel } from "../adapters/mapAnalysisContract";

export type OfflineFormState = {
  recordingRelpath: string;
  metadataRelpath: string;
  transcriptRelpath: string;
};

const INITIAL_FORM: OfflineFormState = {
  recordingRelpath: "",
  metadataRelpath: "",
  transcriptRelpath: "",
};

export function useOfflineAnalysis() {
  const [connection, setConnection] = useState<ConnectionState>("disconnected");
  const [form, setForm] = useState<OfflineFormState>(INITIAL_FORM);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [panelModel, setPanelModel] = useState<OverlayPanelModel | null>(null);
  const [healthNote, setHealthNote] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setConnection("disconnected");
    setErrorMessage(null);
    setPanelModel(null);
    setHealthNote(null);
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const checkHealth = useCallback(async () => {
    setConnection("connecting");
    setErrorMessage(null);
    const result = await bridgeHealth();
    if (!result.ok) {
      setConnection("backend_unavailable");
      setErrorMessage(result.error.message);
      setHealthNote(null);
      return;
    }
    setConnection("disconnected");
    setHealthNote(
      `API reachable · detection model: ${result.detectionModel}` +
        (result.recordingsDirConfigured ? "" : " · recordings dir missing on server"),
    );
  }, []);

  const runAnalysis = useCallback(async () => {
    const payload: AnalyzeOfflineRequestPayload = {
      recordingRelpath: form.recordingRelpath,
      metadataRelpath: form.metadataRelpath,
      transcriptRelpath: form.transcriptRelpath || undefined,
    };
    setConnection("processing");
    setErrorMessage(null);
    setPanelModel(null);

    const result = await bridgeAnalyze(payload);
    if (result.ok) {
      setConnection("completed");
      setPanelModel(mapOfflineAnalysisToPanelModel(result.analysis));
      return;
    }

    if (result.analysis) {
      setPanelModel(mapOfflineAnalysisToPanelModel(result.analysis as OfflineAnalysisDocument));
    }

    if (result.error.code === "validation_error" || result.error.code === "invalid_path") {
      setConnection("validation_error");
    } else if (result.error.code === "backend_unavailable") {
      setConnection("backend_unavailable");
    } else {
      setConnection("analysis_failed");
    }
    setErrorMessage(result.error.message);
  }, [form]);

  return {
    connection,
    form,
    setForm,
    errorMessage,
    panelModel,
    healthNote,
    checkHealth,
    runAnalysis,
    reset,
  };
}
