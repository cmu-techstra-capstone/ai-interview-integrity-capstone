import { useState } from "react";
import type { SuggestedFollowUp } from "../types/session";

type Props = {
  followup: SuggestedFollowUp | null;
  visible: boolean;
};

export function FollowUpQuestions({ followup, visible }: Props) {
  const [copied, setCopied] = useState(false);

  if (!visible || !followup) {
    return (
      <section className="ii-section" aria-label="Suggested follow-up">
        <div className="ii-section-head">
          <h2>Suggested follow-up</h2>
        </div>
        <p className="ii-empty">A sample follow-up will appear after demo analysis.</p>
      </section>
    );
  }

  return (
    <section className="ii-section" aria-label="Suggested follow-up">
      <div className="ii-section-head">
        <h2>Suggested follow-up</h2>
      </div>
      <p className="ii-followup">{followup.text}</p>
      <p className="ii-meta">{followup.sourceLabel}</p>
      <div className="ii-btn-row">
        <button
          type="button"
          className="ii-secondary"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(followup.text);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            } catch {
              setCopied(false);
            }
          }}
        >
          {copied ? "Copied" : "Copy suggestion"}
        </button>
      </div>
    </section>
  );
}
