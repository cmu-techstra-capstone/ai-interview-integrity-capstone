import { describe, expect, it, vi } from "vitest";
import { LocalApiClient } from "./client";
import { assertLoopbackApiBaseUrl, isSafeRelativePath } from "./config";

describe("api config guards", () => {
  it("allows loopback bases only", () => {
    expect(assertLoopbackApiBaseUrl("http://127.0.0.1:8765", ["127.0.0.1", "localhost"]).hostname).toBe(
      "127.0.0.1",
    );
    expect(() => assertLoopbackApiBaseUrl("http://example.com", ["127.0.0.1"])).toThrow();
    expect(() => assertLoopbackApiBaseUrl("http://0.0.0.0:8765", ["0.0.0.0"])).toThrow();
  });

  it("rejects unsafe relative paths", () => {
    expect(isSafeRelativePath("pilot/sample.mp4")).toBe(true);
    expect(isSafeRelativePath("../etc/passwd")).toBe(false);
    expect(isSafeRelativePath("/etc/passwd")).toBe(false);
    expect(isSafeRelativePath("C:\\windows")).toBe(false);
  });
});

describe("LocalApiClient", () => {
  it("maps successful analysis responses", async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          analysis: {
            schema_version: "analysis.v1",
            analysis_id: "anl_x",
            processing_state: "completed",
            source: "offline_processing",
            is_synthetic: false,
            provenance: {
              schema_version: "analysis.v1",
              analysis_id: "anl_x",
              source: "offline_processing",
              is_synthetic: false,
              transcript_mode: "sidecar",
              stt_requested: null,
            },
            answers: [],
            quality_issues: [],
            detection: {
              status: "model_unavailable",
              message: "unavailable",
              confidence_status: "unavailable_not_calibrated",
              confidence_value: null,
              calibrated: null,
              model_name: "aditi-detection",
              model_version: "unavailable",
              review_label: null,
              review_status: null,
              raw_score: null,
              detection_evidence: [],
              related_question_id: null,
              warnings: [],
              error: null,
            },
            errors: [],
            processing_error: null,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new LocalApiClient({}, fetchImpl as unknown as typeof fetch);
    const result = await client.analyzeOffline({
      recordingRelpath: "pilot/a.mp4",
      metadataRelpath: "pilot/a.metadata.json",
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.analysis.detection.status).toBe("model_unavailable");
      expect(result.analysis.detection.confidence_value).toBeNull();
    }
  });

  it("handles backend unavailable", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const client = new LocalApiClient({}, fetchImpl as unknown as typeof fetch);
    const health = await client.health();
    expect(health.ok).toBe(false);
    if (!health.ok) expect(health.error.code).toBe("backend_unavailable");
  });

  it("rejects invalid relative paths before fetch", async () => {
    const fetchImpl = vi.fn();
    const client = new LocalApiClient({}, fetchImpl as unknown as typeof fetch);
    const result = await client.analyzeOffline({
      recordingRelpath: "../secret.mp4",
      metadataRelpath: "pilot/a.metadata.json",
    });
    expect(result.ok).toBe(false);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("handles invalid response payloads", async () => {
    const fetchImpl = vi.fn(
      async () =>
        new Response(JSON.stringify({ ok: true, analysis: { schema_version: "nope" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    const client = new LocalApiClient({}, fetchImpl as unknown as typeof fetch);
    const result = await client.analyzeOffline({
      recordingRelpath: "pilot/a.mp4",
      metadataRelpath: "pilot/a.metadata.json",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("invalid_response");
  });

  it("supports abort/cancellation", async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.signal?.aborted) {
        const err = new DOMException("Aborted", "AbortError");
        throw err;
      }
      await new Promise((r) => setTimeout(r, 20));
      if (init?.signal?.aborted) {
        throw new DOMException("Aborted", "AbortError");
      }
      return new Response("{}", { status: 200 });
    });
    const client = new LocalApiClient({}, fetchImpl as unknown as typeof fetch);
    const controller = new AbortController();
    controller.abort();
    const result = await client.analyzeOffline(
      { recordingRelpath: "pilot/a.mp4", metadataRelpath: "pilot/a.json" },
      controller.signal,
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("aborted");
  });
});
