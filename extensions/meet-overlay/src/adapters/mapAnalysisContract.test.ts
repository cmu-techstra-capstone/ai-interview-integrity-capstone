import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { OfflineAnalysisDocument } from "../types/analysisContract";
import {
  mapDetectionResultState,
  mapOfflineAnalysisToPanelModel,
  mapQualityWarnings,
  mapTranscriptSegments,
} from "./mapAnalysisContract";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(HERE, "..", "..", "..", "..");
const GOLDEN = join(REPO_ROOT, "contracts", "analysis.v1.example.json");

function minimalDoc(
  overrides: Partial<OfflineAnalysisDocument> = {},
): OfflineAnalysisDocument {
  return {
    schema_version: "analysis.v1",
    analysis_id: "anl_test",
    processing_state: "completed",
    source: "offline_processing",
    is_synthetic: false,
    provenance: {
      schema_version: "analysis.v1",
      analysis_id: "anl_test",
      source: "offline_processing",
      is_synthetic: false,
      transcript_mode: "sidecar",
      stt_requested: null,
    },
    answers: [
      {
        interview_id: "INT001",
        participant_id: "P001",
        question_id: "Q01",
        recording_id: "INT001",
        question_text: "Why does software testing matter?",
        transcript: "Um, I think testing matters.",
        question_start: null,
        question_end: null,
        answer_start: 0.5,
        answer_end: 1.5,
        response_latency: null,
        answer_duration: 1.0,
        transcript_segments: [
          {
            id: "Q01-seg-0",
            text: "Um, I think testing matters.",
            start_seconds: 0.5,
            end_seconds: 1.5,
            speaker: "Candidate",
          },
        ],
        has_word_timestamps: true,
        has_segment_timestamps: true,
        audio_timing_features: { speech_rate_wpm: 120 },
        linguistic_features: { filler_word_count: 1 },
        recording_quality_features: { audio_is_silent: false },
        provenance_features: { timing_source: "word_timestamps" },
        evidence_signals: [
          {
            signal_name: "filler_word_count",
            modality: "transcript",
            value: 1,
            quality_status: "ok",
            explanation: "Filled pauses: 1.",
            sample_key: "INT001/Q01",
            source_features: ["filler_word_count"],
          },
        ],
        sample_row: {},
      },
    ],
    quality_issues: [
      {
        severity: "warning",
        code: "MISSING_TRANSCRIPT",
        key: "INT001/Q01",
        message: "no transcript",
      },
    ],
    detection: {
      status: "model_unavailable",
      message: "Aditi's detection model is not integrated yet.",
      confidence_status: "unavailable_not_calibrated",
      confidence_value: null,
      calibrated: null,
      model_name: "aditi-detection",
      model_version: "unavailable",
      review_label: null,
      review_status: null,
      raw_score: null,
      detection_evidence: [],
      related_question_id: "Q01",
      warnings: ["No AI-assistance detection model is available in this build."],
      error: null,
    },
    errors: [],
    processing_error: null,
    ...overrides,
  };
}

describe("mapAnalysisContract", () => {
  it("maps model_unavailable without fabricating scores", () => {
    const model = mapOfflineAnalysisToPanelModel(minimalDoc());
    expect(model.source).toBe("backend");
    expect(model.modeLabel).toBe("OFFLINE ANALYSIS");
    expect(model.isSynthetic).toBe(false);
    expect(model.detection.kind).toBe("model_unavailable");
    expect(model.descriptiveEvidence.length).toBe(1);
    expect(model.descriptiveEvidence[0]?.signalName).toBe("filler_word_count");
    expect(model.question?.id).toBe("Q01");
    expect(mapTranscriptSegments(minimalDoc())[0]?.startSeconds).toBe(0.5);
    expect(mapQualityWarnings(minimalDoc())[0]?.code).toBe("MISSING_TRANSCRIPT");
  });

  it("maps processing failure separately from detection", () => {
    const detection = mapDetectionResultState(
      minimalDoc({
        processing_state: "failed",
        processing_error: "TranscriptionError: simulated",
        answers: [],
      }),
    );
    expect(detection.kind).toBe("failed");
    if (detection.kind === "failed") {
      expect(detection.message).toContain("Offline processing failed");
    }
  });

  it("maps insufficient_evidence and uncalibrated confidence", () => {
    const insufficient = mapDetectionResultState(
      minimalDoc({
        detection: {
          ...minimalDoc().detection,
          status: "insufficient_evidence",
          message: "Not enough evidence for the model.",
          confidence_status: "unavailable_not_provided",
        },
      }),
    );
    expect(insufficient.kind).toBe("insufficient_evidence");

    const available = mapDetectionResultState(
      minimalDoc({
        detection: {
          ...minimalDoc().detection,
          status: "inference_available",
          message: "Mock inference",
          review_label: "Requires human review",
          review_status: "Requires review",
          raw_score: 0.3,
          confidence_status: "unavailable_not_calibrated",
          confidence_value: null,
        },
      }),
    );
    expect(available.kind).toBe("available");
    if (available.kind === "available") {
      expect(available.prediction.confidence.status).toBe("unavailable");
      expect(available.prediction.rawScore).toBe(0.3);
      expect(available.prediction.warnings.some((w) => w.includes("calibrated"))).toBe(
        true,
      );
    }
  });

  it("keeps demo/synthetic documents marked as demo source", () => {
    const model = mapOfflineAnalysisToPanelModel(
      minimalDoc({ source: "demo", is_synthetic: true }),
    );
    expect(model.source).toBe("demo");
    expect(model.modeLabel).toBe("DEMO SIMULATION");
  });

  it("loads Python golden contract when present (Python/TS compatibility)", () => {
    let raw: string;
    try {
      raw = readFileSync(GOLDEN, "utf8");
    } catch {
      // Golden is written by Python test_schema_roundtrip_and_golden_contract_keys.
      // Skip quietly if that test has not run in this environment yet.
      return;
    }
    const doc = JSON.parse(raw) as OfflineAnalysisDocument;
    expect(doc.schema_version).toBe("analysis.v1");
    expect(doc.source).toBe("offline_processing");
    expect(doc.is_synthetic).toBe(false);
    expect(doc.detection.raw_score).toBeNull();
    const model = mapOfflineAnalysisToPanelModel(doc);
    expect(model.source).toBe("backend");
    expect(model.detection.kind).toBe("model_unavailable");
    expect(model.question?.id).toBeTruthy();
    expect(model.revealedSegments.length).toBeGreaterThan(0);
  });
});
