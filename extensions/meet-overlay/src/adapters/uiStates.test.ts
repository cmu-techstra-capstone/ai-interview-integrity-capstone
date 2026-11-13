/**
 * UI-oriented mapping coverage for offline / model-boundary states.
 * Uses the same DetectionAnalysis presentation contract as OverlayApp.
 */

import { describe, expect, it } from "vitest";
import type { OfflineAnalysisDocument } from "../types/analysisContract";
import { mapOfflineAnalysisToPanelModel } from "./mapAnalysisContract";

function baseDoc(): OfflineAnalysisDocument {
  return {
    schema_version: "analysis.v1",
    analysis_id: "anl_ui",
    processing_state: "completed_with_warnings",
    source: "offline_processing",
    is_synthetic: false,
    provenance: {
      schema_version: "analysis.v1",
      analysis_id: "anl_ui",
      source: "offline_processing",
      is_synthetic: false,
      transcript_mode: "none",
      stt_requested: null,
    },
    answers: [
      {
        interview_id: "INT001",
        participant_id: "P001",
        question_id: "Q01",
        recording_id: "INT001",
        question_text: "Describe a hard bug you fixed.",
        transcript: null,
        question_start: 0,
        question_end: 1,
        answer_start: 1,
        answer_end: 3,
        response_latency: 0.2,
        answer_duration: 2,
        transcript_segments: [],
        has_word_timestamps: false,
        has_segment_timestamps: false,
        audio_timing_features: { speech_duration: 0 },
        linguistic_features: {},
        recording_quality_features: { audio_is_silent: true },
        provenance_features: { timing_source: "energy_vad" },
        evidence_signals: [],
        sample_row: {},
      },
    ],
    quality_issues: [
      {
        severity: "error",
        code: "SILENT_AUDIO",
        key: "INT001/Q01",
        message: "audio track is silent",
      },
    ],
    detection: {
      status: "model_unavailable",
      message: "Model unavailable",
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
      warnings: [],
      error: null,
    },
    errors: [],
    processing_error: null,
  };
}

describe("UI states from offline contract", () => {
  it("model unavailable + quality warnings are distinguishable", () => {
    const model = mapOfflineAnalysisToPanelModel(baseDoc());
    expect(model.detection.kind).toBe("model_unavailable");
    expect(model.qualityWarnings.some((w) => w.code === "SILENT_AUDIO")).toBe(true);
    expect(model.source).toBe("backend");
    expect(model.modeLabel).not.toBe("DEMO SIMULATION");
  });

  it("insufficient evidence state", () => {
    const doc = baseDoc();
    doc.detection = {
      ...doc.detection,
      status: "insufficient_evidence",
      message: "Insufficient evidence for detection.",
    };
    const model = mapOfflineAnalysisToPanelModel(doc);
    expect(model.detection.kind).toBe("insufficient_evidence");
  });

  it("failure state from processing_error", () => {
    const doc = baseDoc();
    doc.processing_state = "failed";
    doc.processing_error = "SchemaError: bad timestamps";
    doc.answers = [];
    const model = mapOfflineAnalysisToPanelModel(doc);
    expect(model.detection.kind).toBe("failed");
    expect(model.processingError).toContain("SchemaError");
  });
});
