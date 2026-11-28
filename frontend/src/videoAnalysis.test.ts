import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  AnalysisImportError,
  eventsIn,
  importAnalysis,
} from "./videoAnalysis";

const sample = JSON.parse(
  readFileSync(new URL("../examples/video-analysis.sample.json", import.meta.url), "utf8"),
);
const clone = () => JSON.parse(JSON.stringify(sample));

test("imports the sample written by analyze_video.py", () => {
  const i = importAnalysis(sample, "sample.json");
  assert.equal(i.id, "VA-DEMO-SYNTHETIC");
  assert.equal(i.processing, "Ready");
  assert.equal(i.answers.length, 4);
  assert.deepEqual(
    i.answers.map((a) => a.id),
    ["Q01", "Q02", "Q03", "Q04"],
  );
  assert.ok(i.answers.every((a) => a.score === null), "no score is invented");
  const flagged = i.answers[0];
  assert.equal(flagged.followup?.status, "suggest_followup");
  assert.equal(flagged.question, "Tell me about a project you led.");
  assert.ok(flagged.start > 40 && flagged.end > flagged.start);
  assert.equal(flagged.latency, flagged.followup?.conditions[0].value);
  assert.equal(flagged.followup?.reviewerBriefStatus, "accepted");
  assert.equal(flagged.followup?.reviewerBrief?.suggested_followup_questions.length, 2);
  assert.ok(flagged.signals.some((s) => s.modality === "visual"));
  assert.equal(i.videoAnalysis?.events.length, 3);
  assert.equal(i.videoAnalysis?.calibrationSeconds, 30);
  assert.equal(i.videoAnalysis?.sourceFile, "sample.json");
});

test("rejects files that are not followup_pattern.v1", () => {
  assert.throws(() => importAnalysis({ answers: [] }), AnalysisImportError);
  assert.throws(() => importAnalysis("nope"), AnalysisImportError);
  const wrong = clone();
  wrong.schema = "analysis.v1";
  assert.throws(() => importAnalysis(wrong), /expected schema/);
});

test("refuses any AI-assistance probability", () => {
  const top = clone();
  top.ai_assistance_probability = 0.8;
  assert.throws(() => importAnalysis(top), /probability/);
  const answer = clone();
  answer.answers[0].followup_pattern.ai_assistance_probability = 0.8;
  assert.throws(() => importAnalysis(answer), /probability/);
});

test("never exposes a rejected reviewer brief", () => {
  const rejected = clone();
  rejected.answers[0].followup_pattern.reviewer_brief_status = "rejected";
  const i = importAnalysis(rejected);
  assert.equal(i.answers[0].followup?.reviewerBrief, null);
  assert.equal(i.answers[0].followup?.reviewerBriefStatus, "rejected");
});

test("tolerates missing timings and unknown fields", () => {
  const sparse = clone();
  delete sparse.answers[1].answer_start;
  delete sparse.answers[1].answer_end;
  sparse.answers[1].evidence_signals.push({ modality: "smell", signal_name: "x" });
  sparse.extra = { anything: true };
  const i = importAnalysis(sparse);
  const a = i.answers[1];
  assert.ok(a.end >= a.start);
  assert.ok(a.signals.every((s) => ["audio", "transcript", "visual"].includes(s.modality)));
});

test("unknown follow-up status is an import error", () => {
  const bad = clone();
  bad.answers[0].followup_pattern.status = "cheating";
  assert.throws(() => importAnalysis(bad), /unknown follow-up status/);
});

test("eventsIn includes the pause before an answer", () => {
  const events = [
    { type: "relative_gaze_change", start: 43.5, end: 47 },
    { type: "relative_head_change", start: 120, end: 123 },
  ];
  assert.equal(eventsIn(events, 48, 60).length, 0);
  assert.equal(eventsIn(events, 48, 60, 5).length, 1);
  assert.equal(eventsIn(events, 100, 130).length, 1);
});
