/**
 * Import the post-interview analysis JSON written by
 * `experiments/fusion/analyze_video.py` (schema "followup_pattern.v1") and turn it
 * into the review app's Interview shape.
 *
 * The analysis never carries a score or probability, so imported answers keep
 * `score: null`; the review UI shows the follow-up status and its conditions instead.
 */
import type {
  Answer,
  ConditionStatus,
  EvidenceSignal,
  FollowupCondition,
  FollowupPattern,
  FollowupStatus,
  Interview,
  LookAwayEvent,
  Modality,
  ReviewerBrief,
} from "./data";

export const ANALYSIS_SCHEMA = "followup_pattern.v1";

export class AnalysisImportError extends Error {}

type Json = Record<string, unknown>;
const isObj = (v: unknown): v is Json =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
const str = (v: unknown, fallback = ""): string =>
  typeof v === "string" ? v : fallback;
const strList = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
const spans = (v: unknown): [number, number][] =>
  Array.isArray(v)
    ? v
        .filter(
          (s): s is [number, number] =>
            Array.isArray(s) && num(s[0]) !== null && num(s[1]) !== null,
        )
        .map((s) => [s[0], s[1]] as [number, number])
    : [];

const STATUSES: FollowupStatus[] = [
  "suggest_followup",
  "no_pattern",
  "insufficient_evidence",
];
const CONDITION_STATUSES: ConditionStatus[] = ["met", "not_met", "unmeasurable"];
const MODALITIES: Modality[] = ["audio", "transcript", "visual"];

export const followupLabel: Record<FollowupStatus, string> = {
  suggest_followup: "Suggest follow-up",
  no_pattern: "No pattern",
  insufficient_evidence: "Insufficient evidence",
};
export const followupTone: Record<FollowupStatus, string> = {
  suggest_followup: "coral",
  no_pattern: "teal",
  insufficient_evidence: "neutral",
};
export const conditionLabel: Record<string, string> = {
  delayed_start: "Delayed start",
  look_away: "Look-away",
  fluent_answer: "Fluent answer",
  read_like_delivery: "Read-like delivery",
  ai_like_text: "AI-like text",
};

function toSignal(raw: unknown): EvidenceSignal | null {
  if (!isObj(raw)) return null;
  const modality = str(raw.modality) as Modality;
  if (!MODALITIES.includes(modality)) return null;
  const value =
    typeof raw.value === "number" || typeof raw.value === "string"
      ? raw.value
      : null;
  const quality = str(raw.quality_status, "unknown");
  return {
    signal_name: str(raw.signal_name, "signal"),
    modality,
    value,
    confidence: null,
    quality_status: (["ok", "warning", "unusable", "unknown"].includes(quality)
      ? quality
      : "unknown") as EvidenceSignal["quality_status"],
    supporting_timestamps: spans(raw.supporting_timestamps),
    supporting_transcript_span: null,
    explanation: str(raw.explanation),
    source_features: strList(raw.source_features),
    sample_key: str(raw.sample_key),
  };
}

function toCondition(raw: unknown): FollowupCondition | null {
  if (!isObj(raw)) return null;
  const status = str(raw.status) as ConditionStatus;
  if (!CONDITION_STATUSES.includes(status)) return null;
  return {
    name: str(raw.name),
    required: raw.required !== false,
    status,
    value: num(raw.value),
    threshold: str(raw.threshold),
    explanation: str(raw.explanation),
    timestamps: spans(raw.timestamps),
  };
}

function toBrief(raw: unknown): ReviewerBrief | null {
  if (!isObj(raw)) return null;
  return {
    summary: str(raw.summary),
    observations: Array.isArray(raw.observations)
      ? raw.observations.filter(isObj).map((o) => ({
          text: str(o.text),
          timestamps: spans(o.timestamps),
        }))
      : [],
    alternative_explanations: strList(raw.alternative_explanations),
    suggested_followup_questions: strList(raw.suggested_followup_questions),
    limitations: strList(raw.limitations),
  };
}

function toFollowup(raw: unknown): FollowupPattern {
  if (!isObj(raw)) throw new AnalysisImportError("answer is missing followup_pattern");
  if (raw.ai_assistance_probability !== null && raw.ai_assistance_probability !== undefined)
    throw new AnalysisImportError("analysis must not contain an AI-assistance probability");
  const status = str(raw.status) as FollowupStatus;
  if (!STATUSES.includes(status))
    throw new AnalysisImportError(`unknown follow-up status "${str(raw.status)}"`);
  const briefStatus = str(raw.reviewer_brief_status, "not_requested");
  // Only accepted briefs are ever shown; a rejected one is dropped here as well.
  const accepted = briefStatus === "accepted";
  return {
    status,
    conditions: (Array.isArray(raw.conditions) ? raw.conditions : [])
      .map(toCondition)
      .filter((c): c is FollowupCondition => c !== null),
    reviewerBriefStatus: (["accepted", "rejected"].includes(briefStatus)
      ? briefStatus
      : "not_requested") as FollowupPattern["reviewerBriefStatus"],
    reviewerBrief: accepted ? toBrief(raw.reviewer_brief) : null,
  };
}

function questionLabel(qid: string, index: number): string {
  const m = /^q(\d+)$/i.exec(qid);
  return `Q${String(m ? Number(m[1]) : index + 1).padStart(2, "0")}`;
}

/** Convert a parsed analysis payload into an Interview. Throws AnalysisImportError. */
export function importAnalysis(payload: unknown, fileName = "analysis.json"): Interview {
  if (!isObj(payload)) throw new AnalysisImportError("file is not a JSON object");
  if (payload.schema !== ANALYSIS_SCHEMA)
    throw new AnalysisImportError(
      `expected schema "${ANALYSIS_SCHEMA}" from analyze_video.py, got "${str(payload.schema, "none")}"`,
    );
  if (payload.ai_assistance_probability !== null && payload.ai_assistance_probability !== undefined)
    throw new AnalysisImportError("analysis must not contain an AI-assistance probability");
  const recording = str(payload.recording_id).trim();
  if (!recording) throw new AnalysisImportError("recording_id is missing");
  const rawAnswers = Array.isArray(payload.answers) ? payload.answers : [];
  if (!rawAnswers.length) throw new AnalysisImportError("analysis has no answers");

  const answers: Answer[] = rawAnswers.map((raw, index) => {
    if (!isObj(raw)) throw new AnalysisImportError(`answer ${index + 1} is not an object`);
    const followup = toFollowup(raw.followup_pattern);
    const start = num(raw.answer_start) ?? num(raw.question_end) ?? 0;
    const end = Math.max(start, num(raw.answer_end) ?? start);
    const delayed = followup.conditions.find((c) => c.name === "delayed_start");
    const id = questionLabel(str(raw.question_id), index);
    return {
      id,
      question: str(raw.question_text).trim() || `Question ${index + 1}`,
      start,
      end,
      score: null,
      transcript: [],
      signals: (Array.isArray(raw.evidence_signals) ? raw.evidence_signals : [])
        .map(toSignal)
        .filter((s): s is EvidenceSignal => s !== null),
      speechRate: null,
      latency: delayed?.value ?? null,
      baselineRate: null,
      baselineLatency: null,
      followup,
    };
  });

  const visual = isObj(payload.visual) ? payload.visual : {};
  const events: LookAwayEvent[] = (Array.isArray(visual.events) ? visual.events : [])
    .filter(isObj)
    .map((e) => ({ type: str(e.type), start: num(e.start_s) ?? 0, end: num(e.end_s) ?? 0 }))
    .filter((e) => e.end > e.start);
  const created = str(payload.created_at);
  const source = isObj(payload.source) ? payload.source : {};

  return {
    id: `VA-${recording}`,
    candidate: `Recording ${recording}`,
    role: "Imported analysis",
    team: "Imported",
    interviewer: str(source.video_filename, "Recorded interview"),
    date: /^\d{4}-\d{2}-\d{2}/.test(created)
      ? created.slice(0, 10)
      : new Date().toISOString().slice(0, 10),
    status: "Awaiting review",
    processing: "Ready",
    consent: true,
    quality: "Good",
    answers,
    completedAt: null,
    videoAnalysis: {
      schema: ANALYSIS_SCHEMA,
      events,
      calibrationSeconds: num(visual.calibration_seconds),
      available: visual.available === true,
      disclaimer: str(
        payload.disclaimer,
        "Unvalidated review rule; it does not indicate that the candidate used AI.",
      ),
      sourceFile: fileName,
      importedAt: new Date().toISOString(),
    },
  };
}

export const eventLabel = (type: string) =>
  type === "relative_gaze_change"
    ? "Gaze away"
    : type === "relative_head_change"
      ? "Head turned"
      : type === "no_face_detected"
        ? "Face not visible"
        : type.replaceAll("_", " ");

/** Events overlapping [start, end], optionally widened by `pad` seconds. */
export const eventsIn = (events: LookAwayEvent[], start: number, end: number, pad = 0) =>
  events.filter((e) => e.start < end + pad && e.end > start - pad);
