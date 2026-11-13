# AI-Powered Interview Integrity Monitoring Platform — Project State

> **Single source of truth for the project's current technical state.**
> Last updated: **2026-11-12** (integration branch `feature/end-to-end-integration-v1`
> Phase 6: Meet tab audio → bounded PCM HTTP chunks → localhost FastAPI → STT windows →
> Live UI transcript; research adapters/Aditi remain unavailable-honest).
> Rule: every meaningful change updates this file **in the same PR**. Don't delete past
> decisions; mark them superseded and say why. If this file and the code disagree, the
> code wins. Fix this file.

Repository: `cmu-techstra-capstone/ai-interview-integrity-capstone` (private). The
earlier personal repo `aman-1503/ai-interview-integrity-capstone` is no longer used.

---

## 1. Project Goal

Detect **signals of possible AI assistance** during virtual interviews using transcript,
audio and (later) video evidence. The system gives explainable indicators to support
**human review**, such as whether follow-up questions are warranted. It must **never
automatically declare that a candidate cheated**, and it must not be used for automated
rejection.

---

## 2. Current MVP Architecture

### Implemented

```text
Interview video (local file, shared storage, or streamed from an official public archive)
      ↓
Ingestion            probe, SHA-256, metadata validation, ingest.json
      ↓
Audio extraction     16 kHz mono WAV (atomic, cached per source file)
      ↓
Audio validation     empty → error; silent / noisy / clipped / duration-mismatch flags
      ↓
Transcript interface Transcriber (existing-transcript loader today; STT candidates scaffolded)
      ↓
Q/A segmentation     answer windows from metadata, else search after question_end;
                     timestamps outside the recording are rejected
      ↓
Speech intervals     word timestamps if available, else adaptive energy VAD
      ↓
Features             linguistic + timing + loudness (behavioral) | recording quality (separate)
                     + optional plug-in extractors (visual_/quality_/ext_ namespaces)
      ↓
Validated rows       schema (incl. staged fields), atomic JSONL/CSV, leakage-safe splits
      ↓
Quality report       20 error/warning codes per row and dataset
      ↓
Evidence contract    EvidenceSignal shape + per-modality quality status (no scoring)
```

Supporting infrastructure (implemented):

- **Raw media storage:** raw media is never in Git. Public Michigan clips are streamed
  one at a time from the official archive using HTTP range requests. A storage interface
  (`storage/remote.py`) supports any mounted shared folder, e.g. Drive for Desktop. No
  native Drive/cloud backend exists.
- **Temporary local cache:** `TemporaryCache` caps usage at ≤ 500 MB, checks size before
  downloading, and always deletes on exit. `cache-clean` removes leftovers from killed runs.
- **Docker:** `Dockerfile`, `.dockerignore`, `compose.yaml` (single app container, bind
  mounts only, cache on tmpfs). **Scaffolded but never built** (see §17).
- **Feature plug-ins:** `features/base.py` (`FeatureExtractor`, `AnswerContext`) with
  namespace, collision and scalar-value checks. `features/registry.py` tags every feature
  as behavioral, quality or provenance, with its modality.
- **Service layer:** `services.py` holds every operation as a function returning
  structured results. `cli.py` is a thin wrapper; a test enforces this. This is the
  intended entry point for a future API.
- **Evidence contract:** `evidence.py` and [evidence-contract.md](evidence-contract.md).
  `confidence` is reserved and stays `None`.
- **Google Meet overlay:** Chrome MV3 extension at `extensions/meet-overlay/`.
  Floating launcher/panel on `meet.google.com` via content script + open Shadow DOM.
  Modes: Demo Simulation, Offline Analysis, Live Audio (capture foundation).
  Live STT/classifiers and audio→API transfer are **not** connected yet.
  See [extensions/meet-overlay/README.md](../extensions/meet-overlay/README.md).
- **Offline analysis + extension contract (integration branch):**
  `services.analyze_offline_recording` builds `analysis.v1` (`analysis_contract.py`) from
  existing pipeline outputs + descriptive `EvidenceSignal`s + Aditi detection boundary
  (default `model_unavailable`). Meet overlay maps via `mapAnalysisContract.ts` /
  `OfflineAnalysisPanel`. See [end-to-end-integration.md](end-to-end-integration.md).
- **Localhost FastAPI (Phase 4):** optional `.[api]` extra; loopback-only
  `GET /health` + `POST /v1/analyze-offline`; authorized `RECORDINGS_DIR`; Origin allowlist;
  extension Demo Simulation vs Offline Analysis modes; host permissions Meet +
  `127.0.0.1:8765` / `localhost:8765` only. **Not** a public server.
- **Live Meet tab-audio Phase 6 (2026-11-12):** MV3 `tabCapture` + offscreen PCM
  chunking (~1.5 s) → `POST /v1/live/sessions/.../chunks` → in-memory STT windows
  (fake-live or optional faster-whisper) → Live UI transcript + unassigned speech-window
  features. Research adapters and Aditi remain unavailable. No disk persistence / no
  external upload. See [live-tab-audio-capture.md](live-tab-audio-capture.md).

### Planned (NOT implemented)

| Component | Status |
|---|---|
| Video feature pipeline | not started; only the plug-in interface exists |
| Selected STT implementation | optional baseline approved: faster-whisper small/CPU/INT8; live optional; real Meet+weights unverified here |
| Multimodal fusion / model / scoring | not started; Aditi adapter boundary exists, no production detector |
| Live research classifiers with artifacts | stubs only; HANSEN/ALLSSTAR not bundled |
| Live answer segmentation | speech-window evidence only (unassigned) |
| Post-interview review dashboard | separate branch `feature/frontend-review-mock` (not merged; out of scope for Meet overlay) |
| Review UI (productized / live) | Meet overlay demo + offline + live transcript |
| API layer | localhost FastAPI implemented; remote hosting / auth architecture not approved |
| Persistent database | none; files only; live audio memory-only |
| Production deployment | none |

Details: [architecture.md](architecture.md).

---

## 3. Team Responsibility / Ownership

### Aman (primary ownership)
- project infrastructure
- backend / data-processing infrastructure
- audio pipeline
- dataset / storage processing
- integration infrastructure (connecting transcript, audio and future video pipelines)
- Google Meet Chrome extension frontend (overlay) and related API integration (API not built yet)

### Shared team responsibility
- video pipeline (Aman contributes but is **not** the sole owner)
- final integration
- evaluation
- multimodal system

Other team members' individual ownership has not been recorded yet. A teammate with a
larger machine is expected to run the heavy validation in §17.

---

## 4. Completed Work

| Date | PR | Milestone |
|---|---|---|
| 2026-09-29 | #1 | **Data pipeline foundation:** video ingestion, audio extraction, `Transcriber` interface + loader, linguistic and timing features, dataset schema (assistance vs deception labels separated), JSONL/CSV, participant-grouped splits, CLI, Michigan-safe label rules |
| 2026-09-29 | n/a | Repo moved to the `cmu-techstra-capstone` org; all work since happens there |
| 2026-09-29 | #2 | **Dataset/storage infrastructure:** storage interface, 500 MB temp cache, dataset registry + manifests, remote processing workflow, Michigan manifest (121 clips) from the archive directory only |
| 2026-09-29 | #3 | **Michigan processing:** source-archive streaming, all **121 clips processed** (features only in `processed/`), adaptive VAD threshold (fixed −40 dBFS failed on quiet clips) |
| 2026-10-02 | #4 | **Audio/backend hardening:** audio validation, silence/pause/segment/loudness/recording-quality features, staged-interview schema fields, quality reporting, feature plug-in interface, STT evaluation (`stt-eval`), STT decision doc, Michigan regenerated; 4 bugs fixed |
| 2026-10-03 | #5 | **Docker/STT/staged readiness:** Docker scaffolding, service layer, env config, logging, feature registry, evidence contract, STT adapters + benchmark harness, staged tools (`template`/`import-labels`/`validate`), `process-batch`, `cache-clean`; 5 bugs fixed |

---

## 5. Current Test Status

| Status | What | Result |
|---|---|---|
| ✅ Verified locally (dev laptop) | `pytest -q` (mocked STT; no weight download) | **249 passed** (2026-11-01 Phase 4) |
| ✅ Verified locally | Meet overlay `npm test` + `npm run build` | **25 passed**; dist OK (Meet + loopback API only) |
| ✅ Verified locally | `docker compose config` | valid (no image built or pulled) |
| ✅ Verified locally | CLI smoke: `--help`, `stt-list`, `datasets status`, `staged template/validate`, `cache-clean` | OK |
| ✅ Previously executed | Michigan processed from source (121/121, 0 failures) | on the dev laptop during PRs #3–#4, before the storage-limit rule |
| ⏳ Teammate validation required | Docker build, pytest in container, CLI in container, Michigan regeneration, STT benchmark | see §17 |
| ❌ Not yet executed | any real STT model, any staged recording, any video/visual processing | n/a |

Test growth: 62 (PR #1) → 80 (#2) → 83 (#3) → 136 (#4) → 196 (#5).

---

## 6. Dataset Status

| Dataset | Purpose | Status | AI-assistance label? | Notes |
|---|---|---|---|---|
| UMich Real-life Deception | supporting: deception/audio pipeline data | **processed** (121 clips: 61 deceptive, 60 truthful) | **No:** `UNKNOWN` | features in `processed/`; quality: 0 errors, 15 warnings (6 noisy, 5 clipped, 4 extreme rate); no speaker IDs; committed outputs predate the `audio_duration` column |
| DOLOS | supporting multimodal deception data | **access pending** | **No:** `UNKNOWN` | needs a ROSE Lab account + Release Agreement; 1,675 clips / 213 participants; academic, non-commercial |
| Bag-of-Lies | supporting multimodal deception data | **access pending** | **No:** `UNKNOWN` | needs a licence signed by a CMU legal signatory → databases@iab-rubric.org; 6.14 GB |
| Staged interviews | **the only AI-assistance ground truth** | **preparation** (tooling ready, nothing recorded) | **Yes** (4 conditions) | team-created, consenting participants only |

Deception datasets are **never** AI-assistance ground truth. The schema rejects any
assistance label other than `UNKNOWN` for them. Access details:
[data-storage.md](data-storage.md#access-status-verified-2026-10-03),
`manifests/datasets.json`.

---

## 7. Staged Interview Dataset

Conditions: `HUMAN_UNASSISTED`, `AI_ASSISTED`, `AI_VERBATIM`, `AI_PERSONALIZED`.

| Item | Status |
|---|---|
| Schema | ✅ ready: `question_start/end`, `answer_start/end`, `ai_model_used`, `ai_prompt_used`, `generated_ai_answer`, `response_notes`, `video_reference`, `audio_reference`, `video_sha256`; AI fields optional for human answers |
| Tooling | ✅ `staged template`, `staged import-labels` (TSV, Audacity-compatible), `staged validate`, `process-batch`, multi-question recordings |
| Protocol doc | ✅ drafted: [staged-interviews.md](staged-interviews.md) (IDs `P###`, `STG-P###-S##`, `Q##`; condition definitions; timestamps; AI metadata; consent/privacy) |
| Pilot | ❌ not recorded (target: 2–3 pilot interviews) |
| Decisions needed | condition assignment, separate audio tracks, retention period, IRB (§14) |
| Consent / privacy / retention | ⚠️ principles documented; IRB status and retention period **not decided** |

---

## 8. Audio Pipeline Status

### Implemented features
- **Durations:** answer, speech, silence; `audio_duration`
- **Pauses:** count, long-pause count (≥ 1 s), mean/max/total, std, ratio
- **Speech segments:** count, mean, std
- **Rates:** speech rate and articulation rate (need a transcript); `speech_rate_cv` (needs word timestamps, so currently null)
- **Response latency:** only when `question_end` is known; never estimated
- **Loudness:** speech-level mean, std and range
- **Recording quality (kind=quality, never evidence):** noise floor, speech level, SNR, peak, clipping ratio, silent/noisy/clipped flags
- **Validation:** empty audio → error; impossible timestamps → error; quality issues in the report and in logs

Inventory with calculations: [audio-features.md](audio-features.md).

### Known limitations
- Without word timestamps, timing comes from volume-based VAD; loud background noise counts as speech.
- Interviewer and candidate aren't separated (needs separate tracks, timestamps or diarization).
- Word-level timing, `speech_rate_cv` and filler accuracy depend on the future STT choice.
- Pitch/F0 features aren't implemented; they need a numpy dependency approval.
- Michigan has no speaker IDs, so its splits can't guarantee speaker separation.

---

## 9. Transcript / STT Status

- **Architecture:** provider-independent `Transcriber` interface plus a registry
  (`transcription/registry.py`). Sidecar transcripts remain preferred when present.
  `services.resolve_transcriber()` selects sidecar > explicit STT > none.
- **Optional approved baseline (2026-11-01):** `faster-whisper-small-int8` (and
  `faster-whisper` with the same defaults): model `small`, device `cpu`, compute
  `int8`, word timestamps on, **downloads off** unless `allow_download=true`. Selected
  only via CLI `--stt` / explicit service arguments — **never** the silent default.
  Optional extra: `.[stt-faster-whisper]` (pins `av>=11,<19`). Config:
  [config/stt_baseline.faster_whisper_small_int8.json](../config/stt_baseline.faster_whisper_small_int8.json).
- **Not approved:** WhisperX as default, hosted upload STT, diarization, production
  model-size lock, any scoring/fusion tied to ASR text.
- **Local test status:** mocked unit tests only on the constrained laptop. **No**
  weight download and **no** live faster-whisper inference were run here.
- **Benchmark tooling:** `stt-eval`, `stt-benchmark` unchanged. Leo's research-branch
  20-clip Michigan run (WER ≈ 0.153 for small) is historical evidence, not laptop
  validation. Teammate procedure: [teammate-validation.md](teammate-validation.md) §4.

Details: [stt-decision.md](stt-decision.md).

---

## 10. Video Pipeline Status

- Video pipeline work is a **shared team responsibility**.
- **Integration interface exists:** `FeatureExtractor` plug-ins with `visual_*` (behavioral)
  and `quality_*` (quality) namespaces. See
  [features/visual/README.md](../src/interview_integrity/features/visual/README.md).
- **Stream quality (2026-11-05):** `VideoStreamQualityExtractor` adds ffprobe-only
  `quality_video_*` fields (resolution, fps, codec, low-res flag, answer-window fit).
  On by default via `PipelineConfig.include_video_stream_quality`. **No frames decoded.**
- **No visual model selected or implemented:** no gaze, facial-expression, pose,
  face-recognition, deepfake or visual-cheating models. Raw video is preserved for
  future work.

---

## 11. Backend / Infrastructure Status

| Area | Status |
|---|---|
| Service layer (`services.py`) | ✅ all operations + `analyze_offline_recording`; API-ready |
| Analysis contract (`analysis.v1`) | ✅ Python + TS types; golden example under `contracts/` |
| Detection boundary | ✅ `detection/boundary.py`; default model unavailable; mocks in tests only |
| Localhost API (`api/`) | ✅ FastAPI loopback; health + analyze-offline; path/origin guards |
| CLI (`cli.py`) | ✅ thin wrapper; commands: process, analyze-offline, serve-api, process-batch, … |
| Configuration (`config.py`) | ✅ `INTERVIEW_INTEGRITY_*` env vars |
| Logging | ✅ standard `logging`, global `--log-level` |
| Feature registry | ✅ 30 behavioral + 9 quality + provenance; test fails on unregistered features |
| Storage / cache | ✅ storage interface, local-folder backend, source-archive backend, bounded cache, stale-cache cleanup |
| Docker | ⚠️ scaffolded, not built |
| Dataset validation | ✅ schema, scalar-only features, atomic writes, leakage-safe splits (participant + recording + source checksum) |
| Batch processing | ✅ `process-batch`, `process-remote`, `process-source`; per-recording failures recorded, never fatal |
| Error handling | ✅ explicit errors for empty audio, impossible timing, schema violations, access-restricted datasets |
| Evidence contract | ✅ defined; no scoring |

**Major bugs fixed (all have regression tests):**
- *PR #4:*
  - stale audio reused when a different video shared a `recording_id`
  - cached WAV with the wrong sample rate, or a truncated WAV, was reused
  - noise-only audio reported as 100% speech
  - interviewer's question taken as the answer start (negative latency)
- *PR #5:*
  - a bad feature value wiped `samples.jsonl` (data loss)
  - an invalid manifest row truncated the manifest (data loss)
  - timestamps beyond the recording were accepted
  - rows of one recording split across partitions
  - `process-remote` aborted on the first failure

---

## 12. Storage Strategy

```text
Raw video/audio      → official/remote source or private shared storage (never GitHub)
Temporary processing → teammate machine or appropriate remote infrastructure; the dev laptop
                       is only for small, temporary caches (≤ 500 MB, auto-deleted)
GitHub               → code, configs, manifests, metadata schemas, docs, tiny test fixtures,
                       lightweight public-dataset features (processed/)
```

- **The dev laptop (Aman) has limited storage.** No large datasets, model weights, Docker
  image builds or full-dataset processing there.
- Staged-interview recordings, transcripts and outputs contain personal data. They live
  only in private shared storage, never in Git; `.gitignore` blocks them under `processed/`.
- The shared storage location for staged data (Drive / CMU Box / other) is still open (§14).

---

## 13. Approved Decisions

| Decision | Approved | Notes |
|---|---|---|
| Optional offline STT baseline: faster-whisper `small` / CPU / INT8 + word timestamps; explicit selection only; downloads off by default | 2026-11-01 | Not a scoring model; not auto-run; live inference pending teammate machine |
| Explainable, human-in-the-loop output; no automatic cheating verdicts or rejection | from project start | |
| Modular architecture: ingestion, audio, transcript and (future) video kept separate | from project start | |
| Video-first data; audio + transcript prioritized for the MVP; raw video kept for later | 2026-09-29 | |
| Raw datasets / media never stored in GitHub | 2026-09-29 | |
| All work in the org repo `cmu-techstra-capstone/...`, feature branches + PRs, never push to `main` | 2026-09-29 | personal repo abandoned |
| Michigan (and DOLOS, Bag-of-Lies) are supporting data only; `assistance_label = UNKNOWN` | 2026-09-29 | |
| Staged interviews are required for AI-assistance ground truth | 2026-09-29 | |
| Public datasets are processed by streaming from the official source, committing only lightweight features | 2026-09-29 | **supersedes** "use Google Drive for public datasets" (Drive access wasn't available; streaming avoids storing raw data anywhere). Drive remains an option for restricted/staged data |
| Docker for containerization (no Kubernetes, DBs, servers) | 2026-10-03 | |
| `docs/PROJECT_STATE.md` is the single source of truth, updated in the same PR as each meaningful change | 2026-10-03 | |
| Initial live input = authorized Google Meet **tab audio** via Chrome `tabCapture` (explicit Start/Stop + consent; no mic/desktop picker by default) | 2026-11-12 | |
| Live audio transport = Option A bounded localhost HTTP POST PCM chunks | 2026-11-12 | Inference uses larger STT windows than transport chunks |

---

## 14. Open Decisions

| Decision | Current recommendation (not approved) |
|---|---|
| Final / production STT lock | optional baseline is faster-whisper small/CPU/INT8; revisit after staged pilots |
| STT model size change (`medium` / `large`) | keep `small` until staged + teammate evidence says otherwise |
| Hosted STT usage (even for public audio) | not without explicit approval |
| Separate interviewer/candidate audio tracks | options documented in [staged-interviews.md](staged-interviews.md) |
| Staged condition assignment (e.g. Latin square vs fixed order) | options documented |
| Retention period for staged data | n/a |
| IRB requirements / approval | n/a |
| Shared storage for staged/restricted data (Drive, CMU Box, …) and access method (rclone / Drive API / Drive for Desktop) | Shared Drive + rclone suggested earlier |
| Numeric dependency for pitch features (numpy / parselmouth / librosa) | numpy |
| Database | none needed yet |
| API framework | **Approved for localhost FastAPI** (Phase 4); remote hosting not approved |
| Live audio → FastAPI transport | **Approved Option A** — bounded PCM HTTP POSTs implemented ([live-tab-audio-capture.md](live-tab-audio-capture.md)) |
| Live research classifier artifacts | not bundled; adapters return unavailable |
| Aditi model I/O, labels, calibration, fusion, thresholds | boundary listed; awaiting Aditi confirmation |
| Meet capture / streaming / auth beyond Origin allowlist | not approved |
| Baseline ML model | n/a |
| Multimodal fusion strategy | n/a |
| Scoring formula / confidence thresholds | n/a |
| Semantic-similarity / embeddings model | n/a |
| Video models (gaze, expression, pose, etc.) | n/a |
| Cloud provider / production deployment | n/a |

When one is resolved, move it to §13 with what was chosen and why.

---

## 15. PR / Branch Status

Stacked PRs. Merge strictly in order **#1 → #2 → #3 → #4 → #5**. As of 2026-10-03, none
are merged and none have been reviewed.

| PR | Branch | Base | Purpose | Status |
|---|---|---|---|---|
| [#1](https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone/pull/1) | `feature/data-pipeline-foundation` | `main` | data pipeline foundation | open |
| [#2](https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone/pull/2) | `feature/drive-dataset-storage` | #1 | storage, manifests, remote workflow | open |
| [#3](https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone/pull/3) | `feature/michigan-source-features` | #2 | Michigan from source, 121 clips | open |
| [#4](https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone/pull/4) | `feature/audio-backend-hardening` | #3 | audio/backend hardening, staged schema, quality | open |
| [#5](https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone/pull/5) | `feature/docker-stt-staged-readiness` | #4 | Docker, service layer, STT tooling, staged readiness, this file | open |
| [#10](https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone/pull/10) | `feature/end-to-end-integration-v1` | #5 | STT baseline + Meet overlay + localhost offline API + local harness | open |

---

## 16. Known Issues / Risks

- **Small ground truth:** AI-assistance labels will come only from a small staged dataset, which risks overfitting and weak generalization.
- **Michigan ≠ AI assistance:** misusing deception labels would invalidate results. The schema guards against it; people must too.
- **Audio quality vs behavior:** noise or clipping can distort timing features. Quality is tracked separately and degrades signal trust, but VAD limits remain.
- **Participant/speaker leakage:** guarded by grouped splits. Michigan has no speaker IDs.
- **False positives from future visual cues:** gaze or expression cues are ambiguous and culturally variable.
- **Bias/fairness:** non-native speakers, speech differences and disabilities can affect fluency features.
- **Privacy:** staged recordings are personal data; hosted STT would send audio off-site (not approved).
- **Licensing:** DOLOS and Bag-of-Lies terms restrict use and redistribution; Michigan has no explicit licence.
- **Compute/storage:** the dev laptop can't run heavy jobs, so we depend on the teammate machine.
- **Docker TLS:** Linux `curl` may reject the UMich certificate chain; workaround via `docker/certs/`.
- **Housekeeping:** the old personal repo still exists (deleting it needs the `delete_repo` gh scope), and a stray nested clone sits in the local working dir (untracked).

---

## 17. Needs Teammate Validation

Commands: [teammate-validation.md](teammate-validation.md). Remove items once they're
actually validated and recorded in §5 and §19.

- [ ] Docker image build (+ image size) (§2)
- [ ] `pytest` inside Docker (§2)
- [ ] Docker CLI smoke test (§2)
- [ ] Michigan regeneration (adds `audio_duration`) + quality report (§3)
- [ ] STT benchmark, 20 Michigan clips (§4)
- [ ] Staged pilot dry run, once recordings exist (§5)
- [ ] Future heavy dataset/model processing (DOLOS, Bag-of-Lies, visual work)

---

## 18. Immediate Next Steps

1. **Teammate runs real faster-whisper + Meet verification** using
   [LIVE_STT_TEAMMATE_TESTING.md](LIVE_STT_TEAMMATE_TESTING.md) (this laptop lacks package/weights).
2. **Decide whether to vendor research classifier artifacts** for live audio/text adapters.
3. **Teammate runs the STT benchmark and Docker validation** (validation guide §2 + §4).
4. **Team review and merge of PRs #1–#5**, in order (PR #10 remains stacked on #5).
5. **Team decides the staged-pilot protocol** (condition assignment, audio tracks, retention, IRB), then records 2–3 pilots.
6. **Confirm Aditi model adapter contract** (see `ADITI_CONFIRMATION_NEEDED`).

---

## 19. Change Log

```text
2026-09-29
- PR #1: data pipeline foundation (ingestion, audio, transcript interface, features, schema). 62 tests.
- Repo moved to cmu-techstra-capstone org.
- PR #2: storage interface, temp cache, dataset registry/manifests, remote workflow. 80 tests.
- Google Drive not accessible; public datasets switched to streaming from the official source.
- PR #3: Michigan processed from source (121 clips); adaptive VAD threshold. 83 tests.

2026-10-02
- PR #4: audio validation, expanded audio/timing/loudness/quality features, staged schema,
  quality reporting, plug-in interface, STT evaluation + decision doc; 4 bugs fixed. 136 tests.

2026-10-03
- PR #5: Docker scaffolding (not built), service layer, env config, logging, feature registry,
  evidence contract, STT adapters + benchmark harness, staged pilot tools, process-batch,
  cache-clean; 5 reliability/data-loss bugs fixed. 196 tests.
- Created docs/PROJECT_STATE.md as the single source of truth.

2026-11-01
- Optional STT baseline wiring on `feature/stt-faster-whisper-baseline`: registry name
  `faster-whisper-small-int8`, `services.resolve_transcriber`, docs/config updates.
  Mocked tests only — no local weight download or live inference on the constrained laptop.
- Meet overlay Phase 1 (branch feature/meet-overlay-extension-v1): MV3 Chrome extension
  shell under extensions/meet-overlay/ — floating launcher/panel on meet.google.com,
  open Shadow DOM, React+Vite, demo copy only. No capture, STT, model, or API calls.
- Meet overlay Phase 2 (same branch): simulated interview UI — Start/Pause/Resume/Reset,
  progressive transcript, detection fixture states, sample follow-ups, compact/expanded
  floating sizes. Still no capture, STT, model inference, or backend calls.
- Integration branch `feature/end-to-end-integration-v1`: merges both workstreams above
  on common parent `6e9635c` (docs conflict resolved by retaining both).
- Offline analysis service + analysis.v1 contract + Aditi detection boundary + Meet
  overlay transport-neutral mapping/tests (Phase 3 commit).
- Phase 4: localhost FastAPI + Demo/Offline extension modes
  (`0f95f5e` — Connect FastAPI offline analysis to Google Meet extension).

2026-11-12
- Live Meet tab-audio capture foundation: Live Audio mode, consent + Start/Stop,
  MV3 tabCapture + offscreen, AudioContext playback preserve.
- Phase 6: Option A bounded PCM HTTP chunks → `/v1/live/sessions` API → STT windowing
  (fake-live + optional faster-whisper) → Live UI transcript; research/Aditi unavailable;
  no disk persistence; Demo/Offline preserved.
- Teammate real-STT/Meet guide: docs/LIVE_STT_TEAMMATE_TESTING.md. Real Meet + weights
  not verified on the constrained laptop.
```
