import type { ConnectionState } from "../api/types";
import type { OfflineFormState } from "../offline/useOfflineAnalysis";

type Props = {
  form: OfflineFormState;
  connection: ConnectionState;
  healthNote: string | null;
  errorMessage: string | null;
  onChange: (next: OfflineFormState) => void;
  onCheckHealth: () => void;
  onAnalyze: () => void;
  onReset: () => void;
};

function statusLabel(connection: ConnectionState): string {
  switch (connection) {
    case "disconnected":
      return "Disconnected";
    case "connecting":
      return "Connecting…";
    case "processing":
      return "Processing…";
    case "completed":
      return "Completed";
    case "validation_error":
      return "Validation error";
    case "backend_unavailable":
      return "Backend unavailable";
    case "analysis_failed":
      return "Analysis failed";
    default:
      return connection;
  }
}

export function OfflineAnalysisControls({
  form,
  connection,
  healthNote,
  errorMessage,
  onChange,
  onCheckHealth,
  onAnalyze,
  onReset,
}: Props) {
  const busy = connection === "connecting" || connection === "processing";

  return (
    <section className="ii-section" aria-label="Offline analysis controls">
      <div className="ii-section-head">
        <h2>Offline analysis</h2>
        <span className="ii-pill ii-pill-offline">Not live Meet</span>
      </div>
      <p className="ii-notice">
        Request analysis of an authorized recording already present under the
        server&apos;s configured recordings directory. Relative paths only.
        No browser microphone, tab, or Meet capture.
      </p>
      <p className="ii-meta">
        Status: <strong>{statusLabel(connection)}</strong>
      </p>
      {healthNote && <p className="ii-meta">{healthNote}</p>}
      {errorMessage && (
        <p className="ii-status-error" role="alert">
          {errorMessage}
        </p>
      )}

      <label className="ii-field">
        <span>Recording path (relative)</span>
        <input
          type="text"
          value={form.recordingRelpath}
          disabled={busy}
          placeholder="e.g. pilot/sample.mp4"
          onChange={(e) => onChange({ ...form, recordingRelpath: e.target.value })}
        />
      </label>
      <label className="ii-field">
        <span>Metadata path (relative)</span>
        <input
          type="text"
          value={form.metadataRelpath}
          disabled={busy}
          placeholder="e.g. pilot/sample.metadata.json"
          onChange={(e) => onChange({ ...form, metadataRelpath: e.target.value })}
        />
      </label>
      <label className="ii-field">
        <span>Sidecar transcript (optional, relative)</span>
        <input
          type="text"
          value={form.transcriptRelpath}
          disabled={busy}
          placeholder="e.g. pilot/sample.transcript.json"
          onChange={(e) => onChange({ ...form, transcriptRelpath: e.target.value })}
        />
      </label>

      <div className="ii-btn-row">
        <button type="button" className="ii-secondary" onClick={onCheckHealth} disabled={busy}>
          Check API
        </button>
        <button
          type="button"
          className="ii-primary"
          onClick={onAnalyze}
          disabled={busy || !form.recordingRelpath.trim() || !form.metadataRelpath.trim()}
        >
          Run offline analysis
        </button>
        <button type="button" className="ii-secondary" onClick={onReset} disabled={busy}>
          Clear results
        </button>
      </div>
    </section>
  );
}
