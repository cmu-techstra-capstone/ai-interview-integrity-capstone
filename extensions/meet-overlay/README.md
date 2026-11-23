# Interview Integrity — Google Meet Overlay

Floating Chrome extension that sits **on top of** Google Meet.

**Modes:** Demo Simulation · Offline Analysis · Live Audio (tab capture → localhost STT).

See [`docs/live-tab-audio-capture.md`](../../docs/live-tab-audio-capture.md).

## Modes

### Demo Simulation
- Synthetic fixtures; no backend request; clearly labeled demo

### Offline Analysis
- Relative-path request to localhost FastAPI `POST /v1/analyze-offline`
- Mapped `analysis.v1` results

### Live Audio
- Consent + **Start / Stop Live Audio**
- Meet tab audio via `tabCapture` + offscreen
- Bounded PCM chunks → `POST /v1/live/sessions/{id}/chunks`
- Live transcript from backend (fake-live or optional faster-whisper)
- Independent research cards stay unavailable without artifacts
- Aditi detector remains `model_unavailable`
- No disk recording; no external providers

## Requirements

- Node.js 20+
- Chrome 116+ (tabCapture + offscreen)
- Local FastAPI (`pip install -e ".[api]"`) with extension Origin allowlisted
- Optional: `.[stt-faster-whisper]` + local weights for real STT

## Test & build

```bash
cd extensions/meet-overlay
npm install
npm test
npm run build
```

Load unpacked from `dist/`.

## Manual Meet live check

1. Start API on `127.0.0.1:8765` with `INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS=chrome-extension://<id>`
2. Optionally set `INTERVIEW_INTEGRITY_LIVE_DEFAULT_STT=fake-live` without weights
3. Build + load unpacked extension
4. Join Meet → Live Audio → consent → Start
5. Confirm playback still audible + transcript updates (when STT available)
6. Stop; verify Demo/Offline still work

Full checklist: [`docs/live-tab-audio-capture.md`](../../docs/live-tab-audio-capture.md).
Teammate real-STT + Meet: [`docs/LIVE_STT_TEAMMATE_TESTING.md`](../../docs/LIVE_STT_TEAMMATE_TESTING.md).
