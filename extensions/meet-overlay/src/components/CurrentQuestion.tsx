import type { InterviewQuestion } from "../types/session";

type Props = {
  question: InterviewQuestion | null;
  visible: boolean;
  candidateResponding: boolean;
};

export function CurrentQuestion({ question, visible, candidateResponding }: Props) {
  return (
    <section className="ii-section" aria-label="Current question">
      <div className="ii-section-head">
        <h2>Current question</h2>
        {question && visible ? (
          <span className="ii-pill">{question.id}</span>
        ) : (
          <span className="ii-pill ii-pill-muted">Waiting</span>
        )}
      </div>
      {!visible || !question ? (
        <p className="ii-empty">Start the demo to reveal the interviewer question.</p>
      ) : (
        <>
          {question.askedAtLabel && (
            <p className="ii-meta">Asked at {question.askedAtLabel} (synthetic)</p>
          )}
          <p className="ii-question">{question.text}</p>
          {candidateResponding && (
            <p className="ii-live-flag" role="status">
              Candidate responding… (simulated)
            </p>
          )}
        </>
      )}
    </section>
  );
}
