import type { CaptureSnapshot } from "../types/capture";
import type { LiveResearchResult, LiveTranscriptSegment } from "../types/liveApi";

type Props = {
  snapshot: CaptureSnapshot;
  expanded?: boolean;
};

function ResearchCard({ title, result }: { title: string; result?: LiveResearchResult }) {
  if (!result) {
    return (
      <section className="ii-section" aria-label={title}>
        <div className="ii-section-head">
          <h2>{title}</h2>
          <span className="ii-pill ii-pill-muted">Unavailable</span>
        </div>
        <p className="ii-meta">No research result yet.</p>
      </section>
    );
  }
  return (
    <section className="ii-section" aria-label={title}>
      <div className="ii-section-head">
        <h2>{title}</h2>
        <span className="ii-pill ii-pill-muted">{result.status}</span>
      </div>
      <p className="ii-meta">
        Target: <strong>{result.research_target}</strong>
      </p>
      {result.label ? (
        <p className="ii-review-label">Label: {result.label}</p>
      ) : (
        <p className="ii-meta">No research label (honest unavailable / insufficient evidence).</p>
      )}
      <p className="ii-notice">{result.evidence}</p>
      <p className="ii-meta">Not a cheating probability or rejection recommendation.</p>
    </section>
  );
}

function TranscriptList({
  segments,
  expanded,
}: {
  segments: LiveTranscriptSegment[];
  expanded?: boolean;
}) {
  if (!segments.length) {
    return (
      <p className="ii-empty">
        Waiting for backend transcript updates. Live mode never invents demo words.
      </p>
    );
  }
  return (
    <ul className={`ii-transcript ${expanded ? "ii-transcript-roomy" : ""}`}>
      {segments.map((seg) => (
        <li key={seg.id} className="ii-transcript-item">
          <div className="ii-transcript-meta">
            <span>{seg.speaker || "Candidate"}</span>
            <span>
              {seg.start_seconds.toFixed(1)}s–{seg.end_seconds.toFixed(1)}s
            </span>
            <span>{seg.is_final ? "final" : "partial"}</span>
          </div>
          <p>{seg.text}</p>
        </li>
      ))}
    </ul>
  );
}

export function LiveResultsPanel({ snapshot, expanded = false }: Props) {
  const live = snapshot.live;
  const segments = live?.transcript_segments || [];
  const warnings = live?.quality_warnings || [];
  const features = live?.audio_feature_summary;

  return (
    <div className="ii-live-results">
      <section className="ii-section" aria-label="Live transcript">
        <div className="ii-section-head">
          <h2>Live transcript</h2>
          <span className="ii-pill ii-pill-live">
            {live?.stt_status || "no session"}
          </span>
        </div>
        <p className="ii-notice">
          Words below come from the localhost FastAPI live session only. Aditi detector
          remains unavailable.
        </p>
        <TranscriptList segments={segments} expanded={expanded} />
      </section>

      {warnings.length > 0 && (
        <section className="ii-section" aria-label="Quality warnings">
          <div className="ii-section-head">
            <h2>Quality warnings</h2>
          </div>
          <ul className="ii-quality-block">
            {warnings.map((w) => (
              <li key={w.id}>
                <strong>{w.code}</strong>: {w.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      {features && Object.keys(features).length > 0 && (
        <section className="ii-section" aria-label="Audio speech-window evidence">
          <div className="ii-section-head">
            <h2>Audio speech-window evidence</h2>
            <span className="ii-pill ii-pill-muted">Unassigned</span>
          </div>
          <p className="ii-meta">
            Speech seconds: {String(features.speech_seconds ?? "—")} · intervals:{" "}
            {String(features.speech_interval_count ?? "—")} · pauses:{" "}
            {String(features.pause_count ?? "—")}
          </p>
          <p className="ii-notice">
            {String(features.note || "Not mapped to a candidate answer yet.")}
          </p>
        </section>
      )}

      <ResearchCard title="Audio research (delivery)" result={live?.audio_research} />
      <ResearchCard title="Transcript research (authorship)" result={live?.transcript_research} />

      <section className="ii-section" aria-label="Final detector">
        <div className="ii-section-head">
          <h2>Aditi detector</h2>
          <span className="ii-pill ii-pill-muted">model_unavailable</span>
        </div>
        <p className="ii-meta">
          {live?.detection?.message ||
            "Final detector remains unavailable until an approved live contract is integrated."}
        </p>
        <p className="ii-meta">Confidence: unavailable_not_calibrated</p>
      </section>
    </div>
  );
}
