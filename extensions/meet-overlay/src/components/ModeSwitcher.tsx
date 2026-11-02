export type OverlayMode = "demo" | "offline";

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
      <div className="ii-btn-row" role="group" aria-label="Choose demo or offline analysis">
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
      </div>
      <p className="ii-notice">
        {mode === "demo"
          ? "Synthetic fixtures only — no backend request and no Meet capture."
          : "Uses the localhost offline API for authorized recordings — not live Meet monitoring."}
      </p>
    </section>
  );
}
