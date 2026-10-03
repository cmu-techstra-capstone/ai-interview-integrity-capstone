# AI-Powered Interview Integrity Monitoring Platform — Project State

> **Single source of truth for the project's current technical state.**
> Last updated: **2026-10-03** (through PR #5, branch `feature/docker-stt-staged-readiness`).
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

### Planned (NOT implemented)

| Component | Status |
|---|---|
| Video feature pipeline | not started; only the plug-in interface exists |
| Selected STT implementation | candidates scaffolded; no provider approved |
| Multimodal fusion / model / scoring | not started |
| Review UI | not started |
| API layer | not started; no framework chosen |
| Persistent database | none; files only |
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
| ✅ Verified locally (dev laptop) | `pytest -q` | **196 passed** (2026-10-03) |
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
  (`transcription/registry.py`). Today the only production path is loading existing
  transcripts (`SidecarTranscriber`).
- **Candidates being evaluated:** faster-whisper, WhisperX (adapters with lazy imports;
  packages **not installed**; faster-whisper won't download weights unless
  `allow_download=true`), and hosted APIs (a placeholder that refuses to run without
  explicit approval for external upload).
- **Status:** benchmark tooling exists (`stt-eval`, `stt-benchmark`: WER, filler recall,
  word-timestamp and speaker coverage, speed, memory). **No provider or model approved.**
  Current recommendation, not approved: faster-whisper locally, chosen after the benchmark.
- **Required validation:** 20-clip Michigan benchmark on the teammate machine
  ([teammate-validation.md](teammate-validation.md) §4).

Details: [stt-decision.md](stt-decision.md).

---

## 10. Video Pipeline Status

- Video pipeline work is a **shared team responsibility**.
- **Integration interface exists:** `FeatureExtractor` plug-ins with `visual_*` (behavioral)
  and `quality_*` (quality) namespaces. See
  [features/visual/README.md](../src/interview_integrity/features/visual/README.md).
- **No visual model selected or implemented:** no gaze, facial-expression, pose,
  face-recognition, deepfake or visual-cheating models. Raw video is preserved for
  future work.

---

## 11. Backend / Infrastructure Status

| Area | Status |
|---|---|
| Service layer (`services.py`) | ✅ all operations; API-ready |
| CLI (`cli.py`) | ✅ thin wrapper; commands: process, process-batch, process-remote, process-source, quality, split, staged …, stt-list/eval/benchmark, datasets …, storage-init, cache-clean |
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

---

## 14. Open Decisions

| Decision | Current recommendation (not approved) |
|---|---|
| Final STT provider | faster-whisper, after the benchmark |
| STT model size | benchmark `small` vs `medium` |
| Hosted STT usage (even for public audio) | not without explicit approval |
| Separate interviewer/candidate audio tracks | options documented in [staged-interviews.md](staged-interviews.md) |
| Staged condition assignment (e.g. Latin square vs fixed order) | options documented |
| Retention period for staged data | n/a |
| IRB requirements / approval | n/a |
| Shared storage for staged/restricted data (Drive, CMU Box, …) and access method (rclone / Drive API / Drive for Desktop) | Shared Drive + rclone suggested earlier |
| Numeric dependency for pitch features (numpy / parselmouth / librosa) | numpy |
| Database | none needed yet |
| API framework | none chosen |
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

1. **Teammate runs the STT benchmark and Docker validation** (validation guide §2 + §4). This unblocks the STT decision.
2. **Team review and merge of PRs #1–#5**, in order.
3. **Team decides the staged-pilot protocol** (condition assignment, audio tracks, retention, IRB), then records 2–3 pilots.

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
```
