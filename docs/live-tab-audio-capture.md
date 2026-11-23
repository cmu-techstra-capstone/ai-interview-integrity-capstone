# Live Google Meet tab audio → FastAPI → transcription → floating UI

Branch: `feature/end-to-end-integration-v1`

## Architecture (implemented)

```text
Google Meet — Candidate speaking
      ↓
Chrome tab audio capture (consent + Start/Stop)
      ↓
Offscreen: AudioContext playback + ScriptProcessor PCM tap
      ↓
~1.5 s mono PCM s16le @ 16 kHz (base64)  —— transport interval
      ↓
Service worker → POST /v1/live/sessions/{id}/chunks  (127.0.0.1 only)
      ↓
In-memory session buffer
      ↓
STT on accumulated ~4–8 s windows (overlap ~2 s)  —— inference window ≠ transport chunk
      ├─ Transcript segments (deduped) → Live UI
      └─ Unassigned speech-window audio features → Live UI
      ↓
Independent research adapters (usually model_unavailable)
Aditi detector: model_unavailable
```

**Approved transport:** Option A — bounded HTTP POST PCM chunks. No WebSockets/SSE.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/live/sessions` | Start session (`consent_confirmed`, `meet_tab_confirmed`, optional `stt`) |
| `POST` | `/v1/live/sessions/{id}/chunks` | Accept numbered PCM chunk; returns live snapshot incl. transcript |
| `GET` | `/v1/live/sessions/{id}` | Current snapshot |
| `POST` | `/v1/live/sessions/{id}/stop` | Final flush + clear buffers |

### Chunk payload

```json
{
  "sequence": 1,
  "sample_rate": 16000,
  "channels": 1,
  "encoding": "pcm_s16le",
  "pcm_base64": "...",
  "duration_ms": 1500,
  "client_rel_start_ms": 0
}
```

### Limits (defaults)

- Max concurrent sessions: 2
- Max chunk bytes: 256 KiB
- Max session PCM bytes: 8 MiB
- Session TTL: 30 min; idle TTL: 5 min
- Mono 16-bit PCM only; target 16 kHz

## Consent / capture controls

1. Overlay mode **Live Audio**
2. Consent checkbox
3. **Start Live Audio** (Meet tab only)
4. Visible capturing / transmitting / transcribing statuses
5. Always-visible **Stop Live Audio**
6. Tab close / overlay unmount stops capture and clears the server session

## Data lifecycle

- Audio held in browser offscreen buffer + server `bytearray` only
- Temporary WAV files for STT/VAD are created under system temp and deleted immediately
- **No** default disk retention of interview audio or transcripts
- Stop / timeout / error / API shutdown clears session buffers
- Logs never include PCM or transcript text

## STT windows vs transport chunks

Transport chunks are short (~1–2 s) for bounded POSTs. The processor accumulates audio and
runs STT on larger windows (≥ ~4 s new audio, target ~8 s, overlap ~2 s) so recognition is
not attempted on isolated 1.5 s snippets alone. On Stop, a forced flush runs once.

Partial vs final: current implementation emits **finalized** deduped segments after each
successful window. Overlapping windows are suffix-deduped against previously finalized text.

## Research model statuses

| Adapter | Target | Live status on this branch |
|---|---|---|
| Audio delivery | reading vs spontaneous | `model_unavailable` / `insufficient_evidence` (no ALLSSTAR artifacts) |
| Transcript authorship | AI vs human written-text patterns | same (no HANSEN artifacts) |
| Aditi detector | final interview integrity model | `model_unavailable` |

Outputs are **never** labeled as cheating probabilities.

## Real faster-whisper setup (optional)

```bash
pip install -e ".[api,stt-faster-whisper]"
# Pre-cache weights separately on a machine with disk; do not set allow_download in CI.
export INTERVIEW_INTEGRITY_LIVE_DEFAULT_STT=faster-whisper-small-int8
export INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS=chrome-extension://YOUR_ID
python -m interview_integrity.api
```

If weights/deps are missing, live responses report `stt_unavailable` honestly.

For tests without weights: `stt=fake-live` or `INTERVIEW_INTEGRITY_LIVE_DEFAULT_STT=fake-live`.

## Manual Google Meet walkthrough

1. Start localhost API with origins allowlisted for your unpacked extension ID
2. `cd extensions/meet-overlay && npm ci && npm run build`
3. Load unpacked `dist/` in Chrome; reload after rebuilds
4. Join a real Meet call with audible remote audio
5. Open overlay → **Live Audio** → check consent → **Start Live Audio**
6. Confirm you still hear Meet audio; status moves capturing/transmitting/transcribing
7. Watch **Live transcript** for backend words (requires working STT — fake or real)
8. Confirm audio/transcript research cards show unavailable/insufficient — not fabricated scores
9. **Stop Live Audio**; confirm stopped and no files written under the repo for the session
10. Re-check Demo Simulation and Offline Analysis still work

### Failure recovery expectations

| Situation | Expected |
|---|---|
| API down before Start | Start fails; backend disconnected |
| API dies mid-capture | Chunk upload fails → visible disconnect; capture stops |
| STT missing | `stt_unavailable` with message; no invented words |
| Duplicate/out-of-order chunk | 409 with clear code |
| Oversized/malformed PCM | 400 `invalid_audio` |
| Tab close / unmount | Session stopped + buffers cleared |

## Honest verification status

| Layer | Status |
|---|---|
| Live capture + PCM + localhost transport code | **Implemented** |
| Lightweight Python/TS tests + extension build | **Tested** |
| Synthetic end-to-end (PCM → API → `fake-live` → mapping) | **Tested** (synthetic only) |
| Real faster-whisper on this laptop | **Not verified** (package/weights missing) |
| Real Google Meet browser path | **Not verified** (needs teammate/manual) |
| ALLSSTAR / HANSEN live inference | **Unavailable** (artifacts not bundled) |

Teammate procedure with disk for real STT + Meet:  
**[LIVE_STT_TEAMMATE_TESTING.md](LIVE_STT_TEAMMATE_TESTING.md)**

## Remaining decisions

- Whether to vendor small research classifier artifacts for live inference
- Answer segmentation for live features (currently unassigned speech windows)
- Any additional localhost auth beyond Origin allowlist + loopback Host checks
