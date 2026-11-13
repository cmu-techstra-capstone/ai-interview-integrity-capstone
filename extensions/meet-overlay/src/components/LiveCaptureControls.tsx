import {
  CaptureStatus,
  captureStatusLabel,
  type CaptureSnapshot,
} from "../types/capture";

type Props = {
  consentConfirmed: boolean;
  snapshot: CaptureSnapshot;
  errorMessage: string | null;
  busy: boolean;
  onConsentChange: (checked: boolean) => void;
  onStart: () => void;
  onStop: () => void;
};

function statusClass(status: CaptureSnapshot["status"]): string {
  switch (status) {
    case CaptureStatus.CAPTURING:
    case CaptureStatus.TRANSMITTING:
    case CaptureStatus.TRANSCRIBING:
    case CaptureStatus.STARTING:
      return "ii-status-processing";
    case CaptureStatus.PERMISSION_DENIED:
    case CaptureStatus.ERROR:
    case CaptureStatus.BACKEND_DISCONNECTED:
      return "ii-status-error";
    case CaptureStatus.STT_UNAVAILABLE:
    case CaptureStatus.INTERRUPTED:
      return "ii-status-warn";
    default:
      return "ii-meta";
  }
}

export function LiveCaptureControls({
  consentConfirmed,
  snapshot,
  errorMessage,
  busy,
  onConsentChange,
  onStart,
  onStop,
}: Props) {
  const active =
    snapshot.status === CaptureStatus.CAPTURING ||
    snapshot.status === CaptureStatus.TRANSMITTING ||
    snapshot.status === CaptureStatus.TRANSCRIBING ||
    snapshot.status === CaptureStatus.STARTING;
  const canStart =
    !busy &&
    !active &&
    consentConfirmed &&
    snapshot.status !== CaptureStatus.STARTING;

  return (
    <section className="ii-section" aria-label="Live tab audio capture">
      <div className="ii-section-head">
        <h2>Live Meet audio</h2>
        <span
          className={`ii-pill ${active ? "ii-pill-live" : "ii-pill-muted"}`}
          aria-live="polite"
        >
          {captureStatusLabel(snapshot.status)}
        </span>
      </div>

      <p className="ii-notice">
        Captures <strong>this Google Meet tab&apos;s audio only</strong> after an
        explicit Start. Bounded PCM chunks go to <strong>localhost FastAPI only</strong>.
        Meeting playback stays audible. Audio is not written to disk and is not sent to
        external providers.
      </p>

      <p className={statusClass(snapshot.status)} role="status">
        Status: <strong>{captureStatusLabel(snapshot.status)}</strong>
        {snapshot.message ? ` — ${snapshot.message}` : ""}
      </p>
      <p className="ii-meta">
        Backend:{" "}
        <strong>
          {snapshot.backendConnected === true
            ? "connected"
            : snapshot.backendConnected === false
              ? "disconnected"
              : "unknown"}
        </strong>
        {snapshot.sessionId ? ` · session ${snapshot.sessionId.slice(0, 8)}…` : ""}
        {snapshot.sequence > 0 ? ` · chunks sent ${snapshot.sequence}` : ""}
      </p>

      {errorMessage && (
        <p className="ii-status-error" role="alert">
          {errorMessage}
        </p>
      )}

      <label className="ii-consent">
        <input
          type="checkbox"
          checked={consentConfirmed}
          disabled={active || busy}
          onChange={(e) => onConsentChange(e.target.checked)}
        />
        <span>
          I confirm participants consented to capture of this meeting&apos;s audio
          for interviewer review assistance on this development machine.
        </span>
      </label>

      <div className="ii-btn-row">
        <button
          type="button"
          className="ii-primary"
          onClick={onStart}
          disabled={!canStart}
          aria-label="Start live audio capture"
        >
          Start Live Audio
        </button>
        <button
          type="button"
          className="ii-danger"
          onClick={onStop}
          disabled={busy}
          aria-label="Stop live audio capture"
        >
          Stop Live Audio
        </button>
      </div>

      <p className="ii-meta">
        Does not capture camera, screen video, captions, chat, or other tabs. Research
        classifiers stay independent and unavailable unless explicitly wired with approved
        artifacts.
      </p>
    </section>
  );
}
