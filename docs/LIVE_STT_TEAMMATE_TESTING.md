# Teammate testing: real Meet + faster-whisper (Phase 6)

Branch: `feature/end-to-end-integration-v1`  
PR: [#10](https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone/pull/10)  
Base (stacked): `feature/docker-stt-staged-readiness`

Use a **separate checkout**. Do **not** merge the PR. Do **not** push force.  
Expect several GB free disk for `faster-whisper` + **small** weights.

This guide verifies the path:

```text
Meet remote audio → tabCapture → PCM chunks → localhost FastAPI
  → faster-whisper small CPU INT8 → Live Results Panel
```

Research classifiers (ALLSSTAR / HANSEN) are **not** bundled — expect `model_unavailable`.  
Aditi detector remains unavailable. Outputs are **not** cheating verdicts.

---

## A. Git checkout

```bash
git clone https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone.git
cd ai-interview-integrity-capstone
git fetch origin
git checkout feature/end-to-end-integration-v1
git pull --ff-only origin feature/end-to-end-integration-v1
git rev-parse HEAD   # record this hash in your results
```

Work only on this branch. Do not merge into `main` or into research branches.

---

## B. Python setup

Requires **Python ≥ 3.10** (CI/dev commonly 3.11). From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -U pip
pip install -e ".[api,dev,stt-faster-whisper]"
```

Confirm:

```bash
python -c "import faster_whisper, av, fastapi; print('ok', faster_whisper.__version__)"
```

---

## C. Model setup (approved baseline)

| Setting | Value |
|---|---|
| Registry name | `faster-whisper-small-int8` |
| Size / device / compute | `small` / `cpu` / `int8` |
| Downloads in normal run | **off** (`allow_download=False`) |

One-time weight populate on a machine with disk (uses the existing adapter API):

```bash
source .venv/bin/activate
python - <<'PY'
from interview_integrity.transcription.adapters.faster_whisper import FasterWhisperTranscriber
# allow_download=True ONCE to fill the default Hugging Face / faster-whisper cache.
FasterWhisperTranscriber(
    model_size="small",
    device="cpu",
    compute_type="int8",
    word_timestamps=True,
    allow_download=True,
)
print("small INT8 model ready in local cache")
PY
```

Optional: pin a directory with `download_root="/path/to/models"` on that one-time call, then pass the same path later via:

```bash
# Only if you used a custom download_root above — otherwise omit.
# Live API uses registry defaults (local_files_only); ensure the cache is reachable.
```

Verify local-only load (must succeed **without** network after cache populate):

```bash
python - <<'PY'
from interview_integrity.transcription.registry import create_transcriber
tr = create_transcriber("faster-whisper-small-int8")  # allow_download=False
print("loaded", tr.name)
PY
```

Do **not** commit model weights or cache directories.

---

## D. Backend configuration

Copy `.env.example` → `.env` (never commit `.env`):

```bash
export INTERVIEW_INTEGRITY_API_HOST=127.0.0.1
export INTERVIEW_INTEGRITY_API_PORT=8765
export INTERVIEW_INTEGRITY_LIVE_DEFAULT_STT=faster-whisper-small-int8
# Set AFTER you know the unpacked extension ID (section E):
export INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS=chrome-extension://YOUR_EXTENSION_ID
```

Start FastAPI (loopback only):

```bash
source .venv/bin/activate
python -m interview_integrity.api
# or: interview-integrity serve-api
```

Health check:

```bash
curl -s http://127.0.0.1:8765/health | python -m json.tool
```

Expect `live_audio_enabled: true`, `detection_model: unavailable`.

---

## E. Browser extension

```bash
cd extensions/meet-overlay
npm ci
npm test
npm run build
```

Chrome → `chrome://extensions` → Developer mode → **Load unpacked** → select:

`extensions/meet-overlay/dist`

Copy the extension ID into `INTERVIEW_INTEGRITY_API_ALLOWED_ORIGINS`, restart the API, then **Reload** the extension card.

Confirm `dist/manifest.json` includes permissions `tabCapture` and `offscreen`.

---

## F. Test 1 — Real speech fixture → faster-whisper

Use a **short consented** WAV (16 kHz mono preferred) with known words, e.g. you speaking:  
“The quick brown fox jumps over the lazy dog.”

```bash
source .venv/bin/activate
python - <<'PY'
import time
from pathlib import Path
from interview_integrity.transcription.registry import create_transcriber

wav = Path("PATH/TO/consented_sample.wav")  # replace
assert wav.is_file()
tr = create_transcriber("faster-whisper-small-int8")
t0 = time.perf_counter()
transcript = tr.transcribe(wav)
elapsed = time.perf_counter() - t0
print("text:", transcript.text)
print("provider:", transcript.provider)
print("word_ts:", transcript.has_word_timestamps)
print("seconds:", round(elapsed, 2))
for w in transcript.words[:20]:
    print(f"  {w.start:.2f}-{w.end:.2f} {w.text!r}")
PY
```

Pass criteria: nonempty text; reasonable match to spoken words; timestamps present when enabled; silence-only file should not invent a full sentence.

---

## G. Test 2 — Real audio through live FastAPI (not fake-live)

With the API running and `INTERVIEW_INTEGRITY_LIVE_DEFAULT_STT=faster-whisper-small-int8`:

```bash
source .venv/bin/activate
python - <<'PY'
import base64, json, struct, wave, time
from pathlib import Path
import httpx

wav_path = Path("PATH/TO/consented_sample.wav")
with wave.open(str(wav_path), "rb") as wf:
    assert wf.getsampwidth() == 2 and wf.getnchannels() == 1
    rate = wf.getframerate()
    pcm = wf.readframes(wf.getnframes())
assert rate == 16000, f"resample to 16 kHz mono first; got {rate}"

client = httpx.Client(base_url="http://127.0.0.1:8765", timeout=120.0)
start = client.post("/v1/live/sessions", json={
    "consent_confirmed": True,
    "meet_tab_confirmed": True,
    "stt": "faster-whisper-small-int8",
}).json()
assert start.get("ok"), start
sid = start["live"]["session_id"]

# ~1 s chunks
bytes_per_sec = rate * 2
seq = 1
t0 = time.perf_counter()
for off in range(0, len(pcm), bytes_per_sec):
    chunk = pcm[off:off + bytes_per_sec]
    if not chunk:
        break
    body = {
        "sequence": seq,
        "sample_rate": 16000,
        "channels": 1,
        "encoding": "pcm_s16le",
        "pcm_base64": base64.b64encode(chunk).decode("ascii"),
        "duration_ms": 1000 * len(chunk) / bytes_per_sec,
        "client_rel_start_ms": (seq - 1) * 1000,
    }
    res = client.post(f"/v1/live/sessions/{sid}/chunks", json=body)
    data = res.json()
    print("seq", seq, res.status_code, data.get("live", {}).get("stt_status"),
          "segs", len(data.get("live", {}).get("transcript_segments") or []))
    seq += 1

stop = client.post(f"/v1/live/sessions/{sid}/stop").json()
elapsed = time.perf_counter() - t0
live = stop["live"]
print("status", live.get("status"), "stt", live.get("stt_status"))
print("seconds", round(elapsed, 2))
for s in live.get("transcript_segments") or []:
    print(s.get("start_seconds"), s.get("end_seconds"), s.get("text"))
print("audio_research", live.get("audio_research", {}).get("status"))
print("transcript_research", live.get("transcript_research", {}).get("status"))
print("detection", live.get("detection", {}).get("status"))
PY
```

Pass: `stt_status` becomes `ready` (not `unavailable`); nonempty segments; research/detection unavailable honest; no `.wav` left under the repo.

---

## H. Test 3 — Real Google Meet

1. Start API with correct `API_ALLOWED_ORIGINS` and real STT default.  
2. Load/reload unpacked extension.  
3. Join a **two-person** Meet call with **participant consent**.  
4. Overlay → **Live Audio** → check consent → **Start Live Audio**.  
5. Confirm remote Meet audio remains **audible**.  
6. Remote participant speaks a known sentence for **10–15+ seconds**.  
7. Confirm **Live transcript** shows those words (not Demo fixtures).  
8. Confirm audio/transcript research cards and Aditi show **unavailable** (not fake scores).  
9. **Stop Live Audio** → status stopped; capture ends.  
10. Note approximate speech→transcript latency.

---

## I. Troubleshooting

| Symptom | Check |
|---|---|
| `faster_whisper` import fails | `pip install -e '.[stt-faster-whisper]'` |
| Model not found locally | Re-run one-time `allow_download=True` populate; confirm disk |
| `stt_unavailable` in live API | Package/weights; `LIVE_DEFAULT_STT=faster-whisper-small-int8` (not `fake-live`) |
| `forbidden_origin` | Extension ID in `API_ALLOWED_ORIGINS`; restart API; reload extension |
| Backend unavailable in UI | API on `127.0.0.1:8765`; `api-config.json` loopback |
| No audio / silence | Meet tab focused; remote unmuted; speak longer than ~4s STT window |
| Chunks rejected (`unexpected_sequence`) | Only one live session; Stop then Start cleanly |
| STT slow | Expected on CPU small INT8; note latency; do not switch to hosted STT |
| Demo text in Live mode | Switch mode away/back; Demo must not leak into Live |
| Capture continues after reload | Reload extension again; SW startup closes leftover offscreen docs |

---

## J. Teammate results template

```text
Machine OS:
CPU:
RAM:
Available disk:
Python version:
Browser version:
Commit hash:
Model: faster-whisper-small-int8 (CPU INT8)
Speech fixture result: PASS / FAIL / BLOCKED
  Transcript (redact if needed):
  Timestamps OK?:
  Seconds:
FastAPI live result: PASS / FAIL / BLOCKED
Meet capture result: PASS / FAIL / BLOCKED
Meet playback result: PASS / FAIL / BLOCKED
Live transcript result: PASS / FAIL / BLOCKED
Approximate latency (speech → panel):
Observed errors:
Logs redacted (no PCM/transcript dumps):
Overall: PASS / FAIL / BLOCKED
```

Do not share unauthorized interview audio or full personal transcripts.
