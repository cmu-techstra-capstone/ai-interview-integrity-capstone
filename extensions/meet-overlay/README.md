# Interview Integrity — Google Meet Overlay

Floating Chrome extension that sits **on top of** Google Meet.

**Demo simulation UI only — no audio/video capture, no STT, no model inference, no backend calls.**

## Current phase (Phase 2)

On top of the Phase 1 shell (launcher, drag, minimize/close, Shadow DOM), Phase 2 adds:

- Compact (~360px) and optional expanded (~480px) floating panel sizes
- **Start / Pause / Resume / Reset Demo** controls (explicitly not recording)
- Simulated live interview progression (question → transcript → analysis → follow-up)
- Two synthetic scenarios (ordinary answer vs possible verbatim-style indicators)
- Detection analysis UI with **Confidence: Not calibrated / unavailable**
- Sample follow-up with copy
- Disabled **Full analysis** (“Coming soon”)

## What this does **not** implement

- Real Google Meet capture or DOM scraping of participants/captions
- Aditi’s detection model or any local inference
- Backend HTTP / WebSocket / SSE integration
- Sriya’s post-interview dashboard
- Chrome Side Panel or Meet layout resizing
- Calibrated confidence / cheating probability scores

## Requirements

- Node.js 20+ recommended
- Google Chrome (or Chromium)

## Install

```bash
cd extensions/meet-overlay
npm install
```

Do not commit `node_modules/` or `dist/`.

## Test & build

```bash
npm test          # vitest (demo engine, clamp, capture guards)
npm run build     # typecheck + tests + Vite bundles + dist verify
```

Load unpacked from **`extensions/meet-overlay/dist/`**.

## Load in Chrome

1. `chrome://extensions` → Developer mode → **Load unpacked**
2. Select `extensions/meet-overlay/dist`
3. Open `https://meet.google.com/...`
4. Click the extension toolbar icon → floating launcher
5. Open the panel → **Start Demo**

## Expected demo flow

1. Question appears
2. “Candidate responding…”
3. Transcript segments reveal over time
4. Analysis shows processing, then a synthetic review result
5. Sample follow-up appears
6. Use **Next scenario** for the contrasting example

All content is labeled as demonstration / synthetic.

## Interactions retained from Phase 1

| Control | Behavior |
|---|---|
| Toolbar icon | Opens overlay on Meet |
| Drag | Moves launcher / panel; stays in viewport |
| Expand view / Restore compact | Changes floating panel size only |
| Minimize / Escape | Collapses to launcher (demo state kept in memory) |
| Close | Tears down overlay; timers stop; reopen via toolbar |

## Offline / backend-shaped data (integration branch)

Demo mode is unchanged. Additionally:

- `src/types/analysisContract.ts` mirrors Python `analysis.v1`
- `src/adapters/mapAnalysisContract.ts` maps a document → `OverlayPanelModel` /
  `DetectionResultState` (no HTTP `fetch`)
- `src/panel/OfflineAnalysisPanel.tsx` reuses question / transcript / detection UI
- Golden example: repo `contracts/analysis.v1.example.json`

Default OverlayApp chrome still runs the synthetic demo only. Wiring the loaded
extension to offline JSON or an HTTP API needs explicit approval (permissions,
CORS, auth). See [`docs/end-to-end-integration.md`](../../docs/end-to-end-integration.md).

## Known limitations

- Live Meet UX must be verified manually on your machine
- Demo timing is accelerated for a short walkthrough
- No persistence of panel position
- Full analysis destination is intentionally disabled
- No Meet audio capture; offline contract is not live detection

## Disable / remove

Remove or disable the extension in `chrome://extensions`.
