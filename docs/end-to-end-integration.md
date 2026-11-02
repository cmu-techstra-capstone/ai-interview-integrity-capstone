# End-to-end integration (v1)

Branch: `feature/end-to-end-integration-v1`  
Worktree: sibling checkout `ai-interview-e2e-integration` (do not modify Agent 1/2 worktrees).

This document describes what is **actually implemented** on the integration branch: offline
voice analysis → shared `analysis.v1` contract → transport-neutral Meet overlay mapping.
It does **not** claim live Meet capture, calibrated AI-cheating detection, or an approved HTTP API.

## Unified architecture

```text
Authorized local recording
      ↓
Ingestion + audio validation          (existing)
      ↓
Transcript: sidecar > explicit STT > none
      ↓
Q/A segmentation + timestamps         (existing)
      ↓
Acoustic / timing / linguistic features + quality flags
      ↓
EvidenceSignal descriptions           (descriptive, not proof)
      ↓
Detection boundary                    (default: model_unavailable)
      ↓
analysis.v1 document (JSON)           ProcessResult.analysis_document
      ↓
TypeScript mapAnalysisContract        → OverlayPanelModel / DetectionResultState
      ↓
OfflineAnalysisPanel / DetectionAnalysis   (demo OverlayApp unchanged by default)
```

Later (approval + Aditi adapter required):

```text
Aditi model → DetectionModel.infer → inference_available (optional confidence)
```

## Offline processing flow

Primary entry point:

```bash
# From repo root, with ffmpeg available. No Whisper weights required for sidecar/none paths.
.venv/bin/interview-integrity analyze-offline \
  --video path/to/authorized.mp4 \
  --metadata path/to/recording.metadata.json \
  --transcript path/to/sidecar.transcript.json \   # optional; wins over --stt
  --out-dir data/processed
```

Or in Python:

```python
from interview_integrity.services import analyze_offline_recording

result = analyze_offline_recording(video, metadata, transcript=sidecar_path)
doc = result.to_analysis_dict()  # analysis.v1
```

`process` / `process_local_video` remain unchanged for dataset-row production.

### STT selection and sidecar priority

| Input | Behavior |
|---|---|
| `--transcript` / `transcript=` | Sidecar always wins; STT is not consulted |
| `--stt faster-whisper-small-int8` only | Optional baseline (package + weights required on a capable machine) |
| Neither | Pipeline runs; linguistic features null; timing via energy VAD |

STT is never the silent default. Local CI uses mocked / failing STT only — **no weight download**.

### Processing failure vs detection unavailable

- `processing_error` / `processing_state=failed` → audio/transcript pipeline failed.
- `detection.status=model_unavailable` → Aditi’s model is not wired (default).
- These are independent fields in `analysis.v1`.

## API-facing contract (`analysis.v1`)

- Python: `interview_integrity.analysis_contract`
- TypeScript: `extensions/meet-overlay/src/types/analysisContract.ts`
- Example: [`contracts/analysis.v1.example.json`](../contracts/analysis.v1.example.json)

Includes: schema version, analysis id, processing state, per-answer Q/A + transcript
segments/timestamps, feature groups, quality issues, descriptive evidence, detection
boundary payload, `source` / `is_synthetic`, errors.

**Not included:** fabricated cheating probabilities, simulated production detectors,
Leo’s research classifiers as production engines.

## Model-unavailable behavior

Default detector: `ModelUnavailableDetector` in `detection/boundary.py`.

| Status | Meaning |
|---|---|
| `model_unavailable` | No approved Aditi adapter plugged in |
| `insufficient_evidence` | Adapter present but cannot run (tests / future real model) |
| `model_error` | Adapter raised |
| `inference_available` | Real compatible model returned fields (not fabricated here) |

Confidence defaults to `unavailable_not_calibrated`. `EvidenceSignal` text is **not**
proof of AI assistance.

See **Aditi confirmation list** in `detection/boundary.py` (`ADITI_CONFIRMATION_NEEDED`).

## Extension data mapping

- Mapper: `extensions/meet-overlay/src/adapters/mapAnalysisContract.ts`
- Panel: `extensions/meet-overlay/src/panel/OfflineAnalysisPanel.tsx` (reuses CurrentQuestion,
  LiveTranscript, DetectionAnalysis)
- Demo: `OverlayApp` + `useDemoSimulation` **unchanged** as the default Meet UX

Synthetic demo vs offline:

| | Demo | Offline contract |
|---|---|---|
| `source` | `demo` | `offline_processing` → UI `backend` |
| `is_synthetic` | true (fixtures) | false |
| Mode pill | Demo fixture | Offline analysis |
| Capture | none | none |

No new Chrome host permissions. No `fetch` / WebSocket in the mapping layer.

## HTTP API boundary (awaiting approval)

No HTTP framework is installed or selected in this repo (`pyproject.toml` dependencies = []).

Completed without HTTP:

- Reusable `analyze_offline_recording`
- Serializers (`to_analysis_dict` / `analysis.json`)
- TS mapping + mock-transport tests

### Proposed frameworks (comparison only — not installed)

| Option | Pros | Cons |
|---|---|---|
| **FastAPI** | OpenAPI, Pydantic, async; common for ML services | New dependency; CORS/auth decisions needed |
| **Flask** | Minimal, familiar | Manual OpenAPI; less typed |
| **stdlib `http.server`** | Zero deps | Not production-ready; awkward JSON APIs |
| **Starlette** | Lightweight ASGI | Still a new framework choice |

**Recommendation to discuss:** FastAPI thin wrappers around `services.analyze_offline_recording`
once CORS, auth, host binding, and retention are approved. Until then, use CLI / library calls.

Do **not** add DB, queues, WebSockets, SSE, or polling without explicit approval.

## Tests and reproducibility

```bash
# Python (mocked STT; ffmpeg required for media fixtures)
.venv/bin/python -m pytest -q

# Extension
cd extensions/meet-overlay && npm ci && npm test && npm run build
```

Integration coverage: sidecar precedence, no-STT VAD, multi-question windows, silent audio,
STT failure vs detection, model-unavailable / insufficient / uncalibrated confidence,
schema round-trip, Python↔TS golden contract, demo independence, no capture APIs.

## Offline integration demonstration

1. Use any authorized short recording + metadata (or generate a tiny ffmpeg fixture as in tests).
2. Prefer a sidecar transcript JSON (Whisper-style segments/words) so no STT weights are needed.
3. Run `analyze-offline` and open `data/processed/analysis.json`.
4. Confirm `detection.status` is `model_unavailable` and `is_synthetic` is false.
5. Feed that JSON into `mapOfflineAnalysisToPanelModel` (Node/Vitest) to see overlay view-model fields.

## Known limitations

- No live Google Meet audio capture.
- No Aditi detection inference in production paths.
- No HTTP endpoints.
- faster-whisper live inference not run on the constrained laptop.
- Follow-up questions remain demo/sample only unless separately approved.

## Decisions still needing approval

1. HTTP framework + endpoint shape, CORS, auth, binding.
2. Chrome host / optional permissions beyond current Meet content-script scope.
3. Aditi model I/O schema, labels, confidence calibration, evidence minimums, any fusion/thresholds.
4. Whether OverlayApp should switch into offline panel mode in the loaded extension (vs demo-only chrome).
5. Persistence, jobs, WebSockets/SSE/polling (explicitly out of scope until approved).
