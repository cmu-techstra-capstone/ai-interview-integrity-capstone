import type { DemoPlayStatus } from "../demo/demoEngine";

type Props = {
  status: DemoPlayStatus;
  scenarioTitle: string;
  scenarioKind: string;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onReset: () => void;
  onNext: () => void;
};

export function SessionControls({
  status,
  scenarioTitle,
  scenarioKind,
  onStart,
  onPause,
  onResume,
  onReset,
  onNext,
}: Props) {
  return (
    <section className="ii-section" aria-label="Demo session controls">
      <div className="ii-section-head">
        <h2>Demo controls</h2>
        <span className="ii-pill ii-pill-demo">Not recording</span>
      </div>
      <p className="ii-notice">
        Demonstration only — no Google Meet audio or video is captured by this
        extension.
      </p>
      <p className="ii-meta">
        Scenario: <strong>{scenarioTitle}</strong>
        <span className="ii-dot">·</span>
        <span>{scenarioKind}</span>
        <span className="ii-dot">·</span>
        <span>Status: {status}</span>
      </p>
      <div className="ii-btn-row">
        {(status === "idle" || status === "completed") && (
          <button type="button" className="ii-primary" onClick={onStart}>
            Start Demo
          </button>
        )}
        {status === "running" && (
          <button type="button" className="ii-secondary" onClick={onPause}>
            Pause Demo
          </button>
        )}
        {status === "paused" && (
          <button type="button" className="ii-primary" onClick={onResume}>
            Resume Demo
          </button>
        )}
        <button
          type="button"
          className="ii-secondary"
          onClick={onReset}
          disabled={status === "idle"}
        >
          Reset Demo
        </button>
        <button type="button" className="ii-secondary" onClick={onNext}>
          Next scenario
        </button>
      </div>
    </section>
  );
}
