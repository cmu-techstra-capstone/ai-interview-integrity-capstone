# Interview Integrity — Google Meet Overlay

Floating Chrome extension that sits **on top of** Google Meet.

**Modes:** Demo Simulation (synthetic) and Offline Analysis (localhost API).
**Not live Meet monitoring — no audio/video/caption capture.**

## Modes

### Demo Simulation
- Start / Pause / Resume / Reset Demo controls (explicitly not recording)
- Synthetic question → transcript → analysis → follow-up fixtures
- No backend request

### Offline Analysis
- Explicit relative-path request to the localhost FastAPI (`127.0.0.1:8765`)
- Displays mapped `analysis.v1` results (question, transcript, evidence, quality warnings)
- Shows model unavailable / failures honestly
- Never invents confidence or live Meet claims

See [`docs/end-to-end-integration.md`](../../docs/end-to-end-integration.md) for API setup,
`RECORDINGS_DIR`, and `API_ALLOWED_ORIGINS` (extension ID).

## What this does **not** implement

- Real Google Meet capture or DOM scraping of participants/captions/chat
- Aditi’s detection model inference
- Remote / non-loopback servers
- WebSocket / SSE / polling
- Microphone, camera, tabCapture, or desktopCapture permissions
- Sriya’s post-interview dashboard
- Calibrated confidence / cheating probability scores

## Requirements

- Node.js 20+ recommended
- Google Chrome (or Chromium)
- For Offline Analysis: local FastAPI from the repo (`pip install -e ".[api]"`)

## Install

```bash
cd extensions/meet-overlay
npm install
```

Do not commit `node_modules/` or `dist/`.

## Test & build

```bash
npm test          # vitest
npm run build     # typecheck + tests + Vite bundles + dist verify
```

Load unpacked from **`extensions/meet-overlay/dist/`**.

`dist/api-config.json` defaults to `http://127.0.0.1:8765`. Host permissions are limited to
Meet + that loopback port.

## Load in Chrome

1. `chrome://extensions` → Developer mode → **Load unpacked**
2. Select `extensions/meet-overlay/dist`
3. Copy the extension ID into the API’s `INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS`

### Local harness (no Meet — preferred for quick UI changes)

1. Click the extension toolbar icon on **any non-Meet tab**, **or** open  
   `chrome-extension://<YOUR_EXTENSION_ID>/harness.html`
2. The floating panel opens immediately on a plain local page
3. Use **Demo Simulation** (no API) or **Offline Analysis** (needs localhost API)
4. After `npm run build`, click **Reload** on the extension card, then refresh the harness tab

```bash
npm run harness   # prints these steps
```

### On Google Meet (integration check)

1. Open `https://meet.google.com/...`
2. Click the extension toolbar icon → floating launcher
3. Choose **Demo Simulation** or **Offline Analysis**

## Expected demo flow

1. Question appears
2. “Candidate responding…”
3. Transcript segments reveal over time
4. Analysis shows processing, then a synthetic review result
5. Sample follow-up appears
6. Use **Next scenario** for the contrasting example

All demo content is labeled demonstration / synthetic.

## Offline analysis flow (summary)

1. Start localhost API with authorized recordings directory configured
2. Enter relative paths (recording, metadata, optional sidecar)
3. **Check API** then **Run offline analysis**
4. Review mapped results (model unavailable by default)

## Interactions retained

| Control | Behavior |
|---|---|
| Toolbar icon | Opens overlay on Meet; off Meet opens local harness |
| Drag | Moves launcher / panel; stays in viewport |
| Expand view / Restore compact | Changes floating panel size only |
| Minimize / Escape | Collapses to launcher (in-memory state kept) |
| Close | Tears down overlay; timers stop; reopen via toolbar |

## Known limitations

- Live Meet UX must be verified manually on your machine
- Demo timing is accelerated for a short walkthrough
- No persistence of panel position
- Full analysis destination is intentionally disabled
- Unpacked extension ID must be allowlisted on the API for browser Origins
- Offline mode is not live Meet monitoring
