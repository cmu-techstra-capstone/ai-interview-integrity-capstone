export function FullAnalysisLink() {
  return (
    <section className="ii-section" aria-label="Full analysis">
      <div className="ii-section-head">
        <h2>Full analysis</h2>
        <span className="ii-pill ii-pill-muted">Coming soon</span>
      </div>
      <p className="ii-empty">
        The post-interview full analysis experience is not connected yet. This
        control stays disabled until a real destination exists.
      </p>
      <button type="button" className="ii-secondary" disabled>
        Open full analysis
      </button>
    </section>
  );
}
