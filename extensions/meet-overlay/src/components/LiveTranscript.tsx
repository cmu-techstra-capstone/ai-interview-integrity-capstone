import { useEffect, useRef } from "react";
import type { TranscriptSegment } from "../types/session";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0");
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

type Props = {
  segments: TranscriptSegment[];
  expanded: boolean;
};

export function LiveTranscript({ segments, expanded }: Props) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [segments.length]);

  return (
    <section className="ii-section" aria-label="Live transcript">
      <div className="ii-section-head">
        <h2>Live transcript</h2>
        <span className="ii-pill ii-pill-demo">Synthetic</span>
      </div>
      {segments.length === 0 ? (
        <p className="ii-empty">Transcript segments will appear as the demo runs.</p>
      ) : (
        <ul className={`ii-transcript ${expanded ? "ii-transcript-roomy" : ""}`}>
          {segments.map((segment, index) => {
            const current = index === segments.length - 1;
            return (
              <li
                key={segment.id}
                className={current ? "ii-transcript-item is-current" : "ii-transcript-item"}
              >
                <div className="ii-transcript-meta">
                  <time>{formatTime(segment.startSeconds)}</time>
                  <span>{segment.speaker}</span>
                </div>
                <p>{segment.text}</p>
              </li>
            );
          })}
          <div ref={endRef} />
        </ul>
      )}
    </section>
  );
}
