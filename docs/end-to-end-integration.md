# End-to-end integration (v1 → Phase 4 local API)

Branch: `feature/end-to-end-integration-v1`
Worktree: sibling checkout `ai-interview-e2e-integration` (do not modify Agent 1/2 worktrees).

This document describes what is **actually implemented**: offline voice analysis →
`analysis.v1` → **localhost FastAPI** → Meet overlay **Demo Simulation** /
**Offline Analysis** modes, plus the separate **Live Audio capture foundation**
(tab audio hold only — see [live-tab-audio-capture.md](live-tab-audio-capture.md)).

It does **not** claim live transcription, live classification, calibrated AI-cheating
detection, remote hosting, or Aditi model inference.

## Unified architecture

```text
Authorized local recording (under RECORDINGS_DIR)
      ↓
Localhost FastAPI  POST /v1/analyze-offline   (127.0.0.1 only)
      ↓
services.analyze_offline_recording
      ↓
sidecar | explicit STT | none → features → EvidenceSignal → detection boundary
      ↓
analysis.v1 JSON (paths sanitized for clients)
      ↓
Extension service worker (allowlisted loopback fetch)
      ↓
mapAnalysisContract → OfflineAnalysisPanel
```

Demo Simulation remains a separate, synthetic path with **no** backend request.

## Local FastAPI (Phase 4)

Optional install:

```bash
uv venv .venv && uv pip install -e ".[dev,api]" --python .venv/bin/python
# or: pip install -e ".[dev,api]"
```

### Configuration

| Variable | Purpose | Default / notes |
|---|---|---|
| `INTERVIEW_INTEGRITY_API_HOST` | Bind host | **Must** be `127.0.0.1` or `localhost` |
| `INTERVIEW_INTEGRITY_API_PORT` | Port | `8765` |
| `INTERVIEW_INTEGRITY_RECORDINGS_DIR` | Authorized recordings root | `data/authorized_recordings` |
| `INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS` | CORS + Origin allowlist | Comma-separated `chrome-extension://<id>` (required for browser Origin) |

Copy `.env.example` → `.env` (never commit `.env`).

After loading the unpacked extension, copy its ID from `chrome://extensions` into
`INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS=chrome-extension://YOUR_ID`.

Extension loopback URL: `extensions/meet-overlay/public/api-config.json`
(copied into `dist/` on build). Default `http://127.0.0.1:8765`.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness; reports detection model unavailable; **no** filesystem paths |
| `POST` | `/v1/analyze-offline` | Offline analysis using **relative** paths under `RECORDINGS_DIR` |
| `POST` | `/v1/live/sessions` | Start in-memory live audio session (consent + Meet affirmation) |
| `POST` | `/v1/live/sessions/{id}/chunks` | Bounded PCM chunk; returns live transcript snapshot |
| `GET` | `/v1/live/sessions/{id}` | Current live snapshot |
| `POST` | `/v1/live/sessions/{id}/stop` | Stop + clear buffers |

Request body:

```json
{
  "recording_relpath": "pilot/sample.mp4",
  "metadata_relpath": "pilot/sample.metadata.json",
  "transcript_relpath": "pilot/sample.transcript.json",
  "stt": null
}
```

Success: `{ "ok": true, "analysis": { ... analysis.v1 ... } }`
Errors: `{ "ok": false, "error": { "code": "...", "message": "..." } }` (no stack traces / absolute paths).

### Security controls

- Bind loopback only (`python -m interview_integrity.api` / `serve-api` refuses non-loopback).
- Host middleware rejects non-loopback `Host` headers.
- Origin allowlist for browser `Origin` (CORS is not authentication).
- Relative paths only; reject `..`, absolute paths, unsupported types.
- Resolve with `realpath` and reject symlink escapes outside the recordings root.
- Ephemeral temp dirs per request; no upload retention; no database.
- Do not log transcript text; sanitize absolute paths in client JSON.

### Startup

```bash
export INTERVIEW_INTEGRITY_RECORDINGS_DIR="$PWD/data/authorized_recordings"
export INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS="chrome-extension://YOUR_EXTENSION_ID"
.venv/bin/python -m interview_integrity.api
# or: .venv/bin/interview-integrity serve-api
```

Stop with Ctrl-C.

## Offline processing flow (library / CLI)

```bash
.venv/bin/interview-integrity analyze-offline \
  --video path/to/authorized.mp4 \
  --metadata path/to/recording.metadata.json \
  --transcript path/to/sidecar.transcript.json \
  --out-dir data/processed
```

STT: sidecar wins; explicit `--stt faster-whisper-small-int8` optional; neither → VAD-only.

## Extension modes

| Mode | Behavior |
|---|---|
| **Demo Simulation** | Synthetic fixtures; no API calls; labeled demo |
| **Offline Analysis** | Explicit user request → service worker → localhost API → mapped results |
| **Live Audio** | Consent + Start/Stop → PCM chunks → localhost live STT windows → transcript UI |

Offline UI states: disconnected, connecting/processing, completed, validation error,
backend unavailable, analysis failed.

Live capture states: stopped, starting, capturing, permission_denied, interrupted, error.

Content script never fetches arbitrary URLs; the service worker only calls the configured
loopback base for offline analysis. Host permissions: Meet + `127.0.0.1:8765` +
`localhost:8765`. Capture permissions: `tabCapture`, `offscreen` (no `desktopCapture`).

Live PCM transport is **Option A** (bounded HTTP POSTs). Details:
[live-tab-audio-capture.md](live-tab-audio-capture.md).
Real faster-whisper + Meet teammate procedure:
[LIVE_STT_TEAMMATE_TESTING.md](LIVE_STT_TEAMMATE_TESTING.md).

## Model-unavailable behavior

Default detector remains `ModelUnavailableDetector`. Confidence stays
`unavailable_not_calibrated`. EvidenceSignal descriptions are measurements, not proof.

## Manual development walkthrough

1. Create venv and install `.[dev,api]` (see above). Ensure `ffmpeg` is available.
2. Place an authorized short recording + metadata (+ optional sidecar transcript) under
   `data/authorized_recordings/` (relative paths only, e.g. `pilot/sample.mp4`).
3. Start the API on `127.0.0.1:8765` with `RECORDINGS_DIR` and `API_ALLOWED_ORIGINS` set.
4. `cd extensions/meet-overlay && npm ci && npm run build`
5. Chrome → `chrome://extensions` → Developer mode → Load unpacked → select `dist/`
6. Copy the extension ID into `INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS` and restart the API.
7. Open `https://meet.google.com/` (any Meet page).
8. Click the extension toolbar icon → open the floating panel.
9. Choose **Offline Analysis** → enter relative paths → **Check API** → **Run offline analysis**.
10. Confirm results show offline labels, model unavailable, and quality/evidence separation.
11. Switch back to **Demo Simulation** (synthetic path; no API).
12. Stop the API (Ctrl-C).

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Origin not allowed / 403 | Extension ID missing from `API_ALLOWED_ORIGINS` |
| Backend unavailable | API not running, wrong port, or `api-config.json` mismatch |
| file_not_found | Relative path wrong or file outside `RECORDINGS_DIR` |
| invalid_path | Absolute path or `..` segments |
| Host not allowed | Non-loopback Host header / misconfigured proxy |

Never describe this workflow as live Google Meet monitoring.

## Tests and reproducibility

```bash
.venv/bin/python -m pytest -q
cd extensions/meet-overlay && npm test && npm run build
```

Coverage includes path traversal/symlink guards, CORS/origin, health + analyze endpoints,
API client mapping, demo independence, and no capture permissions.

## Known limitations

- No live Google Meet audio/video/caption capture.
- No Aditi detection inference in production paths.
- Localhost development API only (not a public deployment).
- faster-whisper live inference not validated on the constrained laptop.
- Unpacked extension ID must be configured manually for Origin allowlisting.
- Actual Chrome Meet UX should be verified manually on a developer machine.

## Decisions still awaiting approval

1. Remote hosting / non-loopback bind.
2. Authentication architecture beyond Origin allowlisting + loopback.
3. Aditi model I/O, labels, calibration, fusion, thresholds.
4. Real-time Meet capture / streaming / WebSockets / SSE / polling.
5. Broadening Chrome host permissions or ports beyond 8765.
6. Committing Phase 4 changes (when you approve).
