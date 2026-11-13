export type OverlayMode = "demo" | "offline" | "live";

type Props = {
  mode: OverlayMode;
  onChange: (mode: OverlayMode) => void;
};

export function ModeSwitcher({ mode, onChange }: Props) {
  return (
    <section className="ii-section" aria-label="Overlay mode">
      <div className="ii-section-head">
        <h2>Mode</h2>
      </div>
      <div className="ii-btn-row" role="group" aria-label="Choose demo, offline, or live capture">
        <button
          type="button"
          className={mode === "demo" ? "ii-primary" : "ii-secondary"}
          aria-pressed={mode === "demo"}
          onClick={() => onChange("demo")}
        >
          Demo Simulation
        </button>
        <button
          type="button"
          className={mode === "offline" ? "ii-primary" : "ii-secondary"}
          aria-pressed={mode === "offline"}
          onClick={() => onChange("offline")}
        >
          Offline Analysis
        </button>
        <button
          type="button"
          className={mode === "live" ? "ii-primary" : "ii-secondary"}
          aria-pressed={mode === "live"}
          onClick={() => onChange("live")}
        >
          Live Audio
        </button>
      </div>
      <p className="ii-notice">
        {mode === "demo"
          ? "Synthetic fixtures only — no backend request and no Meet capture."
          : mode === "offline"
            ? "Uses the localhost offline API for authorized recordings — not live Meet monitoring."
            : "Authorized Google Meet tab audio → localhost FastAPI chunks → live transcript. Research classifiers stay independent/unavailable unless artifacts are present."}
      </p>
    </section>
  );
}
