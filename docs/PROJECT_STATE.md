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
  mounts only, cache on tmpfs). **Built and tested on Linux arm64** with local
  configuration-copy fix and extras `dev,ml` on 2026-10-07 (see §5).
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
| ✅ Verified on teammate machine | Native `pytest -q` on PR #5 base | **196 passed**, 0 failures/skips; macOS arm64, Python 3.13.7 (2026-10-06) |
| ✅ Verified on teammate machine | Michigan regeneration + independent quality check | **121 processed, 0 failed; 0 errors, 15 warnings across 14 clips**; `audio_duration` present in all rows (2026-10-06) |
| ✅ Verified with local fixes | Native suite and Docker suite, including optional audio ML tests | **205 passed each**, 0 failures/errors/skips (2026-10-07) |
| ✅ Verified after ALLSSTAR importer | Native suite, including 16 new importer tests | **221 passed**, 0 failures/errors/skips; 4.93 s (2026-10-07); Docker remains at the earlier 205-test image |
| ✅ Verified after optional VAD/prosody research | Native suite, including 19 new tests and extractor smoke checks | **240 passed**, 0 failures/errors/skips; 14.19 s (2026-10-07); Docker still at the earlier 205-test image |
| ✅ Verified after local recording prediction | Native suite, including 19 new inference tests | **259 passed**, 0 failures/errors/skips; 8.24 s (2026-10-07); Docker remains at 205 tests |
| ✅ Verified after local transcript baseline | Native suite, including 35 new mechanics tests | **294 passed**, 0 failures/errors/skips; 10.27 s (2026-10-07); two offline ASR-to-detector smoke tests completed; Docker remains at 205 tests |
| ✅ Verified after frozen-transcript comparison | Native suite, including 40 new comparison tests | **334 passed**, 0 failures/errors/skips; 11.27 s with clean exit on standalone rerun (2026-10-07). Earlier concurrent run passed assertions but aborted at native teardown; cause unresolved. Docker remains at 205 tests |
| ✅ Verified after public paired-text benchmark | Native suite, including 35 new benchmark tests | **369 passed**, 0 failures/errors/skips; clean exit in 16.42 s (2026-10-08). Heavy encoder/head parity test isolated in a checked subprocess; earlier native teardown abort retained. Docker remains at 205 tests |
| ✅ Executed locally | Beemo external written-text stress test | 200 frozen groups, three variants, three models; 1,800 rows, 0 inference errors, hashes verified. 90 common complete groups; six AUROCs cross-checked with scikit-learn; not audio/interview validation |
| ✅ Verified after detector follow-up | Native tests, publisher cleanup and Fast-DetectGPT | **391 tests passed**, final clean exit in 16.69 s; 1,200 cleanup rows + 600 Fast-DetectGPT rows, 0 errors, exact same 90 groups. Both reports' AUROCs cross-checked; all 600 cleaned inputs match each publisher source. Smaller GPT-Neo baseline original/edited AUROC 0.8535/0.6116; Docker not rebuilt |
| ✅ Verified after verbatim pilot mechanics | Native tests and partial local audio/ASR diagnostic | **418 tests passed**, clean exit, 23.59 s; two recordings and two pure-text controls transcribed/scored/repeated. Source/text hashes and scores identical; reading subsequently user-confirmed AI-verbatim, speaking independent; human self-script control still missing. First ASR teardown aborted; clean retry retained. No audio accuracy estimate; Docker not rebuilt |
| ✅ Verified after Desklib integration | Native suite, strict architecture/loading checks and model/contrast-subset benchmark support | **426 tests passed**, 0 failures/errors/skips (2026-10-22); pinned 1.7 GB weights cached locally; Docker not rebuilt |
| ✅ Verified after HANSEN research-only experiments | Native suite, including HANSEN archive parsing, leakage-audited baseline and aggregate-only CLI tests | **431 tests passed** (2026-10-26); no product API changes; Docker not rebuilt |
| ✅ Executed locally | Desklib Beemo original-AI stress test | 200 frozen groups evaluated; 103 complete human/original-AI pairs; AUROC **0.8705** [0.8267, 0.9133], 92.2% paired ordering; written-text benchmark only |
| ✅ Verified with local fixes | Docker build + container CLI smoke | Linux arm64 image, 288,175,847 bytes; help/dataset status/STT list/audio-baseline help OK (2026-10-07) |
| ✅ Executed locally | 20-clip faster-whisper small, medium, prompted small benchmarks | 20/20 success each; WER 0.1534 / 0.1593 / 0.1462; see validation report for filler limitations |
| ✅ Executed locally | WhisperX small aligned benchmark | **20/20 success**, WER 0.1711, filler recall 0/9; trusted CA/NLTK fix; diarization not tested |
| ✅ Executed locally | ALLSSTAR reading/spontaneous audio baseline | 862 windows, 140 speakers; five-fold speaker-separated balanced accuracy **0.739**, reading F1 **0.488**, ROC AUC **0.812**; not an AI-use detector |
| ✅ Executed locally | ALLSSTAR paired VAD/prosody comparison, eight arms | Same 862 windows/folds; original metrics reproduced exactly. Silero/prosody SVM: balanced accuracy **0.834**, F1 **0.663**, AUC **0.907**, FPR **12.3%**; exploratory, not an independent test |
| ✅ Executed locally | Standalone video research | **7 focused tests passed**; two-worker public-clip smoke checks; all 138 MIT videos processed at 2 fps, 95,945 measurements, 0 errors. Full native suite/Docker not rerun. |
| ❌ Not yet executed | Interview AI-assistance classifier training, staged cohort validation or video/backend integration | Direction/delivery-mode evaluation does not establish AI detection |

Test growth: 62 (PR #1) → 80 (#2) → 83 (#3) → 136 (#4) → 196 (#5).

Teammate validation details and reproduction commands:
[native tests and Michigan report](../reports/pr5_validation/README.md).
Follow-up: [Docker and STT validation](../reports/pr5_validation/validation-20261007.md).
Audio model: [ALLSSTAR first experiment](../reports/allsstar/first-run-20261007.md).
Follow-up model comparison: [VAD and prosody results](../reports/allsstar/prosody-vad-20261007.md).

---

## 6. Dataset Status

| Dataset | Purpose | Status | AI-assistance label? | Notes |
|---|---|---|---|---|
| UMich Real-life Deception | supporting: deception/audio pipeline data | **regenerated locally 2026-10-06** (121 clips: 61 deceptive, 60 truthful) | **No:** `UNKNOWN` | features in `processed/`; `audio_duration` present in all 121 rows; quality: 0 errors, 15 warnings across 14 clips (6 noisy, 5 clipped, 4 extreme rate); no speaker IDs |
| ALLSSTAR English | reading/spontaneous audio delivery research | **downloaded manually, ZIP CRC verified; NWS/ST1/ST2 imported and baseline fitted locally 2026-10-07** | **No** | local inventory: 1,163 WAV, 963 TextGrid, 140 speakers; ZIP 9.89 GiB; selected 418 recordings produced 862 windows (148 reading / 714 spontaneous), 0 decode failures; QNA excluded |
| Beemo | external written-text detector stress test | **public parquet downloaded and paired benchmark completed locally 2026-10-08** | **AI-origin text labels, NOT verified real-time interview use** | 8,345,056-byte parquet, 2,187 groups; 200 selected before inference, three variants; 90 common complete groups. Human-edited AI text remains a project AI-assisted positive. No audio; training overlap not fully auditable |
| HANSEN Turing Test | spoken-style human/original-LLM transcript stress test | **request submitted and 95 MB TT archive downloaded 2026-10-22; two research evaluations completed** | **Human vs generated spoken-style text; NOT interview-use ground truth** | Desklib: 3,472/11,594 scored (29.9%); AUROC 0.9941 on scored subset. TF-IDF/LR: leakage-audited, deduplicated test AUROC 0.9985 at 100% coverage. Research-only; not interview-use ground truth. |
| MIT Interview Dataset | interview audio/video and component transfer testing | **located in Andrew email and downloaded 2026-10-29**; 138 videos / 69 people, approximately 13.3 locally decoded hours; all videos processed | **No AI-assistance label** | Video ZIP CRC and source hashes checked. P/PP is pre/post counseling. Valid answer windows and directed calibration are still needed. |
| Cheating Scenario Dataset | head/eye direction components | 770 verified frames, 3 people; participant-separated experiments completed | **Direction labels only** | Scripted directions; not AI-use labels. |
| Columbia Gaze | gaze-direction component validation | 1,176 images / 56 people; grouped classifier and known-target calibration comparisons completed | **Gaze-target labels only** | Center-calibrated S0 AUC 0.8824 on 1,120 scored images; calibration images excluded. |
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
- Pitch/F0 variability is implemented only in the optional research workflow via
  selected eGeMAPS descriptors; the standard pipeline still has no pitch extractor.
- Michigan has no speaker IDs, so its splits can't guarantee speaker separation.

### Research classifier

The optional `modeling/audio_baseline.py` trains `READING` versus `SPONTANEOUS`
delivery from 14 audio-only features, with optional transcript-derived rates. It
requires explicit ground truth and known pseudonymous participants, separates
quality/provenance from model inputs, and fits imputation/scaling inside grouped
folds. Eight synthetic tests verify mechanics. The first real ALLSSTAR model is
fitted locally: balanced accuracy 0.739, reading F1 0.488, ROC AUC 0.812. The
spontaneous-to-reading false-positive rate is 27.9% at the default threshold;
task and interview-domain generalization remain unvalidated. See the
[experiment report](../reports/allsstar/first-run-20261007.md). Michigan deception
labels cannot fill the delivery-label requirement.

The optional `modeling/audio_experiment.py` preserves the original 862-window
cohort and source checksums while comparing energy/Silero VAD with and without
20 prosody descriptors, using Logistic Regression and RBF SVM. Original features
and metrics reproduce exactly, and every arm uses identical speaker folds.
Silero/prosody SVM reduces FPR to 12.3% with reading recall 79.1%; energy/prosody
Logistic Regression has the highest balanced accuracy (0.837). No production
selection is approved. Seven Silero no-speech windows and 20 generated listening
examples await human audit. openSMILE commercial integration needs licence review.
See [workflow](audio-delivery-experiment.md) and
[results](../reports/allsstar/prosody-vad-20261007.md).

Manual local prediction is now available through `modeling/audio_predict.py`.
It uses the fixed Silero/prosody SVM and reports per-window decision margins,
not probabilities. Personal smoke-test outputs remain private; they are not
independent performance validation or permission to deploy the classifier.

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

Optional local research now also includes `modeling/transcript_baseline.py`:
candidate-only audio -> existing faster-whisper small -> pinned pretrained HC3
text detector. Its provisional ASR configuration is not a production STT decision.
All inference is local; outputs stay ignored. The diagnostic personal examples
had counterintuitive scores, so no detection accuracy, threshold, calibrated
AI-assistance score, or deployment readiness is claimed. See
[transcript baseline](transcript-baseline.md) and the four-condition pilot template.

`modeling/text_comparison.py` adds a separate optional comparison of three pinned
checkpoints on frozen sidecars, without another ASR pass or publisher-specific
cleanup. Score semantics differ (MAGE machine=0; HC3 ChatGPT=1; SuperAnnotate one
GENERATED sigmoid). All models still gave low scores to a colloquial synthetic
AI answer. This remains diagnostic, not model selection or interview validation;
see [text comparison](text-model-comparison.md).

`modeling/beemo_benchmark.py` adds an optional public written-text benchmark,
reusing these adapters without ASR or retraining. Paired AUROC decreases after
expert editing for all three models; HC3 is near chance on the edited contrast.
Length guards exclude 55% of selected groups from complete comparisons (only
2 Closed QA groups remain), so report coverage and avoid a general accuracy claim.
See [aggregate Beemo report](../reports/beemo/paired-text-20261008.md).

---

## 10. Video Pipeline Status

- Video pipeline work is a **shared team responsibility**.
- **Integration interface exists:** `FeatureExtractor` plug-ins with `visual_*` (behavioral)
  and `quality_*` (quality) namespaces. See
  [features/visual/README.md](../src/interview_integrity/features/visual/README.md).
- **Stream quality (2026-11-05):** `VideoStreamQualityExtractor` adds ffprobe-only
  `quality_video_*` fields (resolution, fps, codec, low-res flag, answer-window fit).
  On by default via `PipelineConfig.include_video_stream_quality`. **No frames decoded.**
- **Research visual layer (Leo, merged via the research PR, 2026-11-27):** post-interview
  head-pose (MediaPipe) and gaze (frozen Gaze360-trained MobileOne-S0) measurements,
  baseline-relative look-away events, a deterministic follow-up rule (delayed start +
  look-away + fluent vs own median) and an optional guarded LLM reviewer brief.
  One command per recording: `experiments/fusion/analyze_video.py` -> dashboard JSON.
  Not wired into the live Meet path; no face recognition, expression or deepfake models;
  `ai_assistance_probability` stays null. Details: [demo-handoff.md](demo-handoff.md),
  [followup-pattern.md](followup-pattern.md), [video report](../reports/video/video-research-20261029.md).
  Gaze360-derived weights are non-commercial research only and stay out of Git.

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
| Docker | ✅ built and tested on Linux arm64, with local copy fix; extras `dev,ml` |
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

**Current (2026-11-27):** PR #10 landed the end-to-end trunk on `main` (2026-11-23) and the stacked
PRs #1-#5 were closed. Leo's research work (former PRs #6, #9, #11: audio/transcript research,
HANSEN, video + follow-up + LLM brief, synthetic positives) is ported onto `main` in the branch
`leo/research-on-main` for review. The table below is the historical stacked order.

Stacked PRs. Integration dependency order is **#1 → #2 → #3 → #4 → #5 → #6**.
All are open as of 2026-10-08; review status is not audited here. PR #6 targets
PR #5's branch to isolate the research delta, not to duplicate it against main.
No PR was merged or another author's branch changed during research publication.

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

- [x] Docker image build (+ image size) (§2): local copy fix; 288,175,847 bytes, Linux arm64
- [x] `pytest` inside Docker (§2): 205 passed, including optional ML tests
- [x] Docker CLI smoke test (§2): help, dataset status, STT list, audio-baseline help
- [x] Michigan regeneration (adds `audio_duration`) + quality report (§3): completed natively on 2026-10-06; results in §5 and §19
- [x] STT benchmark, 20 Michigan clips (§4): four local configurations completed 20/20 each; limitations in validation report; no provider approved
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
2026-11-27
- Ported Leo's research workstream (former PRs #6/#9/#11) onto main after PR #10 landed:
  156 files (142 new). Conflicts resolved in pyproject.toml (both extras kept), stt-decision.md
  (main's approved baseline kept, research benchmark appended) and this file (main kept, research
  summarised in sections 10 and 15).

2026-11-17
- One-recording post-interview analysis: experiments/fusion/analyze_video.py (video + speaker-labelled
  transcript -> dashboard JSON; fusion/analyze.py, fusion/transcript_input.py). P1 matches the batch run;
  3-minute video from scratch in 27 s on 4 CPU cores.

2026-11-12
- Branch published to GitHub with demo export (fusion/demo_export.py), MIT reviewer-brief script
  (experiments/fusion/brief_mit.py) and docs/demo-handoff.md for building the demo on PR #10.

2026-11-05
- Synthetic-positive pipeline (synthetic/, llm/openrouter implemented + cache): AI_VERBATIM /
  AI_PERSONALIZED / AI_SPOKEN answers to MIT questions from 3 model families, blind content rubric by a
  4th-family judge, participant-grouped AUROC. Content channel only; synthetic rows never become
  assistance_label. Team approved sending MIT answer text to OpenRouter. 620 eligible answers / 69
  participants. See synthetic-positives.md. Must run on the Mac (sandboxes cannot reach OpenRouter).
- Timeline fusion prototype (fusion/turns, followup, llm_brief) + 24 tests; MIT run: 909 answer
  windows, 569 with reliable timing, 18/324 flagged (5.6%). Not integrated into product APIs.

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
