# AI-Powered Interview Integrity Monitoring Platform — Project State

> **Single source of truth for the project's current technical state.**
> Last updated: **2026-10-08** (PR #5 base plus validation/fixes and audio/text research published in [PR #6](https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone/pull/6), branch `codex/audio-transcript-research`).
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
- **Research audio trainer:** optional `audio-baseline` CLI for explicitly labeled
  reading/spontaneous delivery, participant-grouped evaluation and Logistic Regression.
  First real ALLSSTAR baseline fitted locally: 862 windows, 140 speakers, five-fold
  speaker-separated balanced accuracy 0.739. It is separate from
  evidence scoring and does not detect AI use. See [audio-baseline.md](audio-baseline.md).
- **ALLSSTAR importer:** local ZIP/directory ingestion for English read/spontaneous
  task labels, stable speaker IDs, fixed audio windows and quality reporting.
  Full English ZIP verified; NWS/ST1/ST2 imported and baseline trained locally. See
  [ALLSSTAR audio baseline](allsstar-audio.md).
- **Audio VAD/prosody experiment:** optional Silero ONNX speech intervals and 20
  selected eGeMAPS descriptors; paired LR/SVM comparison completed locally on the
  same 862 windows and speaker folds. Silero/prosody SVM: balanced accuracy 0.834,
  FPR 12.3%, reading recall 79.1%; human VAD audit and interview transfer pending.
  No default pipeline or production model changed. See
  [experiment results](../reports/allsstar/prosody-vad-20261007.md).
- **Local audio prediction:** `modeling/audio_predict.py` tests the fixed research
  Silero/prosody SVM on local recordings with training-matched 30-second windows.
  Reports margins, quality flags and no-speech abstention; expected delivery is
  comparison metadata only. Personal recordings/results stay in ignored data
  directories. No ASR, retraining, UI/API or AI-use scoring is added.
- **Local transcript-detector prototype:** separate `transcript-baseline` command
  reuses faster-whisper small locally, preserves unedited transcripts, and applies
  pinned HC3 RoBERTa weights. English/length/channel-quality guards; no truncation,
  calibrated confidence, verdict, training, fusion, or remote inference. Two private
  recording smoke tests completed with counterintuitive score ordering and ASR
  terminology errors; interview performance remains unvalidated. See
  [workflow and limitations](transcript-baseline.md).
- **Frozen-transcript candidate comparison:** optional `transcript-compare`
  compares pinned HC3, MAGE and SuperAnnotate locally on identical existing
  answer text; correct label order and strict custom-head loading verified.
  Four private diagnostic samples completed and repeated exactly; the colloquial
  AI-generated answer remains a low-score blind spot across all three. No model
  winner, training, threshold, calibrated score or production integration. See
  [protocol and limitations](text-model-comparison.md).
- **Public paired-text benchmark:** optional `beemo-benchmark` freezes 200 prompt
  groups from pinned Beemo before offline scoring; human/original-AI/expert-edited-AI
  variants remain paired. Completed 1,800 rows with no inference errors; 90 common
  complete groups. Original AI AUROC 0.693-0.745; expert-edited AI 0.507-0.623,
  conditional on retained texts. No threshold/model selected or interview accuracy
  claimed. See [aggregate results](../reports/beemo/paired-text-20261008.md).
- **Fixed-input detector follow-up:** optional `detector-followup` checks reviewed
  checksum-pinned MAGE/SuperAnnotate publisher preprocessing on the original Beemo
  cohort. Completed 1,200 rows, no errors; all original 90 complete groups retained.
  Edited-text AUROC remains weak: MAGE cleanup 0.6304 (softmax), SuperAnnotate 0.6378.
  The smaller local GPT-Neo Fast-DetectGPT baseline completed 600 rows, 397 scored,
  0 errors; same 90 groups, original/edited AUROC **0.8535/0.6116**. Original-text
  ranking improves here, edited-text weakness remains. No training, confidence/verdict, threshold,
  fusion or production changes. See [follow-up results](../reports/beemo/detector-followup-20261008.md).
- **Verbatim audio/ASR diagnostic:** optional `verbatim-pilot` separates fresh
  same-settings ASR and cached Fast-DetectGPT inference, freezes source/provenance
  and transcript hashes, and excludes pure-text controls from the audio cohort.
  Two personal recordings + two text controls completed/repeated, identical scores,
  no inference errors. User subsequently confirmed reading as AI-verbatim and
  speaking as independent (self-reported, after scoring). Three-condition validation
  remains incomplete: independent self-scripted reading missing. First ASR teardown
  aborted after verified outputs; new retry exited cleanly with identical hashes.
  No threshold/accuracy claim. See [pilot status](../reports/verbatim/pilot-status-20261008.md).
  Primary MVP handoff: [audio/transcript research update](audio-transcript-research-update.md),
  focusing on original AI vs independent human responses; human-edited/paraphrased
  AI remains outside this phase's headline evaluation, not a human-negative label.

### Planned (NOT implemented)

| Component | Status |
|---|---|
| Video feature pipeline | not started; only the plug-in interface exists |
| Selected STT implementation | candidates scaffolded; no provider approved |
| Multimodal fusion / validated AI-assistance model / scoring | not started; standalone audio-delivery and pretrained text-detector research prototypes exist, neither validated for AI-assistance decisions |
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
| ✅ Verified with local fixes | Docker build + container CLI smoke | Linux arm64 image, 288,175,847 bytes; help/dataset status/STT list/audio-baseline help OK (2026-10-07) |
| ✅ Executed locally | 20-clip faster-whisper small, medium, prompted small benchmarks | 20/20 success each; WER 0.1534 / 0.1593 / 0.1462; see validation report for filler limitations |
| ✅ Executed locally | WhisperX small aligned benchmark | **20/20 success**, WER 0.1711, filler recall 0/9; trusted CA/NLTK fix; diarization not tested |
| ✅ Executed locally | ALLSSTAR reading/spontaneous audio baseline | 862 windows, 140 speakers; five-fold speaker-separated balanced accuracy **0.739**, reading F1 **0.488**, ROC AUC **0.812**; not an AI-use detector |
| ✅ Executed locally | ALLSSTAR paired VAD/prosody comparison, eight arms | Same 862 windows/folds; original metrics reproduced exactly. Silero/prosody SVM: balanced accuracy **0.834**, F1 **0.663**, AUC **0.907**, FPR **12.3%**; exploratory, not an independent test |
| ❌ Not yet executed | AI-assistance classifier training, staged recordings or video/visual processing | Delivery-mode evaluation does not establish AI detection |

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
  (`transcription/registry.py`). Today the only production path is loading existing
  transcripts (`SidecarTranscriber`).
- **Candidates being evaluated:** faster-whisper, WhisperX (adapters with lazy imports;
  packages optional; installed locally for teammate validation; faster-whisper won't download weights unless
  `allow_download=true`), and hosted APIs (a placeholder that refuses to run without
  explicit approval for external upload).
- **Status:** benchmark tooling exists (`stt-eval`, `stt-benchmark`: WER, filler recall,
  word-timestamp and speaker coverage, speed, memory). Three faster-whisper variants
  completed 20 clips each on 2026-10-07; WhisperX also completed 20/20 after SSL/NLTK setup fixes.
  **No provider or model approved.**
  Current recommendation, not approved: faster-whisper locally, chosen after the benchmark.
- **Evaluation limitation:** the guide's first 20 clips are all deceptive courtroom
  clips. There are only 9 standard reference fillers, and the prompted model emitted
  25 with 8 count matches. Do not treat filler recall alone as reliable preservation
  or word timestamp coverage as boundary accuracy.

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
| Baseline ML model | Paired VAD/prosody LR/SVM comparison completed; Silero/prosody SVM is a low-FPR research candidate (12.3%), not production-approved; human audit, independent task/interview validation and licence review remain; no AI model or scoring threshold approved |
| Multimodal fusion strategy | n/a |
| Scoring formula / confidence thresholds | n/a |
| Semantic-similarity / embeddings model | n/a |
| Video models (gaze, expression, pose, etc.) | n/a |
| Cloud provider / production deployment | n/a |

When one is resolved, move it to §13 with what was chosen and why.

---

## 15. PR / Branch Status

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
| [#6](https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone/pull/6) | `codex/audio-transcript-research` | #5 | audio/transcript research tools, verbatim pilot, validation and aggregate reports | open |

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

1. **Review the completed STT results**; decide on provider only after considering filler hallucinations, sample selection and timing limitations.
2. **Team review and merge of PRs #1–#5**, in order.
3. **Team decides the staged-pilot protocol** (condition assignment, audio tracks, retention, IRB), then records 2–3 pilots.
4. **Audit the ALLSSTAR VAD/prosody comparison**: listen to the 20 private examples,
   review seven Silero no-speech windows, then evaluate held-out tasks and controlled
   interview delivery. The candidate's 12.3% false-positive rate is not interview-ready.
   Michigan deception labels remain separate; neither dataset supplies AI-use ground truth.

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

2026-10-06
- Teammate validation on codex/pr5-michigan-validation, based on PR #5 commit 6e9635c.
- Native suite: 196 passed, zero failures/errors/skips; Python 3.13.7 on macOS arm64.
- Michigan regenerated from the official archive: 121 processed, 0 failed, 308.0 MB fetched.
- All 121 audio and combined rows now contain audio_duration; labels/transcripts unchanged.
- Independent quality check: 0 errors, 15 warnings across 14 clips. No raw media retained.
- Recorded FFmpeg 9.0.2 and small existing-feature differences in reports/pr5_validation/README.md.
- Docker/STT benchmarks, staged pilots and classifier training remain pending; no PR merge
  status or reviewed defects were resolved by this validation.

2026-10-07
- Docker built locally; reproduced 3 missing-config test failures, fixed explicit COPY,
  rebuilt with dev,ml. Native and Linux arm64 container suites both pass 205 tests.
- Reproduced faster-whisper/PyAV 19 decoding incompatibility; bound PyAV below 19,
  verified 18.1.0. Benchmark now reports failed/partial instead of misleading ok.
- Added per-language alignment cache to WhisperX with regression coverage.
- Three faster-whisper configs completed the same 20 Michigan clips; reports saved.
- WhisperX hit alignment/NLTK certificate-download failures; verified CA bundle and
  cached official resources resolved them. 20/20 clips completed; TLS checks retained.
- Added optional audio-baseline trainer, ground-truth CSV template and 8 synthetic tests.
  No real reading/spontaneous or Michigan proxy classifier fitted yet.
- At the end of the earlier validation run, no ALLSSTAR request, hosted audio upload,
  new PR, commit or push had been performed; ALLSSTAR status is superseded below.

2026-10-07 ALLSSTAR follow-up
- Requested the initial English subset and then all English tasks with user authorization.
  Northwestern generated download notifications for both requests.
- Official catalog: 1,163 English WAV, 963 TextGrid, 140 speakers, 42.02 hours, 9.95 GB.
- Browser full-folder and small-file downloads failed with Invalid InterceptionId;
  direct anonymous HTTP returned 403. No complete local dataset verified or training run.
- Added local ALLSSTAR importer, strict filename/task/speaker validation, ZIP safeguards,
  fixed nonoverlapping audio windows and explicit quality/error output.
- NWS/ST1/ST2 selected initially; QNA refused until candidate-only segmentation exists.
- Importer and existing audio trainer: 24 synthetic regression tests passed.
  Full native suite: 221 passed, no failures/errors/skips, 4.93 s. Test report:
  reports/pr5_validation/native-tests-allsstar-20261007.xml.
  These are software tests, not real detection scores. No commit, push or new PR.

2026-10-07 ALLSSTAR first real experiment
- User supplied the manually downloaded 2982.zip. Moved it into ignored
  data/raw/allsstar/english-full.zip; original removed from Downloads by the move.
- Local archive: 10,615,555,746 bytes; 1,163 WAV, 963 TextGrid, 140 speakers;
  full-archive CRC passed. Supersedes the automatic-download blocker above.
- Imported NWS/ST1/ST2: 418 selected, 408 with usable windows, 862 windows across
  140 speakers. Ten recordings too short, two silent/no-separable windows excluded;
  zero decode failures. Five retained windows have noise flags.
- Reading 148 / spontaneous 714; 132 speakers have usable windows in both classes.
- Fitted audio-only class-balanced Logistic Regression with 14 features, no ASR.
  Five-fold participant-grouped evaluation, zero speaker overlap in every fold:
  balanced accuracy 0.7390, reading F1 0.4880, ROC AUC 0.8122.
  Spontaneous false positives 199/714 (27.9%); not an AI-use detector.
- Saved and smoke-tested trusted local model; raw ZIP/features/models remain ignored.
  Aggregate results: reports/allsstar/first-run-20261007.md.
  No external audio upload, commit, push or new PR.

2026-10-07 ALLSSTAR VAD and prosody comparison
- Added optional research-only Silero ONNX adapter and 20 selected eGeMAPS descriptors.
  Original pipeline/default baseline unchanged; no ASR, transcript or task inputs.
- Reprocessed the same 408 source recordings / 862 windows, zero failures;
  source checksums matched and original energy features/metrics reproduced exactly.
- Eight fixed LR/SVM arms share identical five-fold speaker assignments.
  Silero/prosody SVM: balanced accuracy 0.8336, reading F1 0.6629, AUC 0.9067;
  spontaneous false positives 88/714 (12.3%), reading recall 117/148 (79.1%).
  Energy/prosody LR has highest balanced accuracy (0.8374); no production selection.
- VAD disagreement mean 3.01 s/window; seven Silero no-speech detections retained.
  Created 20 private error/control audio examples and timeline review page;
  human review CSV remains blank. No VAD timestamp ground truth established.
- Native suite: 240 passed, 0 failures/errors/skips; Docker remains at 205 tests.
  All eight trusted local models reload/predict; raw/derived audio and models ignored.
- Results: reports/allsstar/prosody-vad-20261007.md. Independent task/interview
  validation and commercial openSMILE licensing remain open. No commit/push/PR.

2026-10-07 Local manual audio prediction
- Added fixed-model inference with complete 30-second windows, source/model
  checksums, quality flags and no-speech abstention. No ASR or retraining.
- Expected delivery labels are user-reported evaluation metadata, not predictors.
  Private recordings and detailed results stay under ignored raw/processed data.
- Two personal recordings processed locally as a functional smoke test; no
  population accuracy claim. Native suite: 259 passed, 0 failures/errors/skips.
  Docker not rebuilt; no external audio upload, commit, push or PR.

2026-10-07 Local audio-to-transcript detector prototype
- Added a separate optional `transcript-baseline` CLI using local faster-whisper
  and pinned pretrained HC3 RoBERTa; no retraining or change to core services.
- Safe weights-only loading, verified label order, candidate-only confirmation,
  language/word/token/quality guards, no silent truncation or LLM cleanup.
- Two existing private recordings completed offline inference; counterintuitive
  score ordering and ASR terminology errors retained as diagnostic limitations.
  Reading/spontaneous labels do not establish AI-use ground truth.
- Added running/interpretation documentation and a four-condition pilot planning
  template. Native suite: 294 passed (35 new), 0 failures/errors/skips, 10.27 s.
- Model weights, audio, transcripts and detailed outputs remain Git-ignored;
  no hosted inference, content upload, fusion, calibrated verdict, commit/push/PR.
  Docker not rebuilt; interview accuracy and licensing review remain open.

2026-10-07 Direct synthetic-transcript writing-style diagnostic
- User requested one conversational-style approximation and one standard GPT
  answer on the same technical topic. BOTH were assistant-generated; neither is
  real human ground truth. Inputs were fixed before inference; no post-score edits.
- Same pinned HC3 detector, 120/122 words and 142 tokens each, no ASR or truncation.
  Both outputs strongly favored Human, including the standard AI-generated answer.
  This is a diagnostic failure case, not population accuracy or a causal style test.
- Inputs, generation provenance and results remain under ignored data/processed;
  no model/pipeline/threshold changed, no training, content upload or commit/push.
  Last native software suite remains 294 passing tests; no new tests added.

2026-10-07 Frozen-transcript candidate model comparison
- Added optional transcript-compare download/run CLI. HC3, MAGE and SuperAnnotate
  revisions pinned; only local inference, no ASR rerun, source rewriting or training.
- Verified MAGE machine=0/human=1 against author source; saved raw logits without
  applying publisher cutoff. Reconstructed SuperAnnotate's single-logit head,
  loading its complete safetensors state strictly; no remote custom code executed.
- Compared the same two existing recording transcripts and two synthetic answers.
  BOTH synthetic answers are AI-generated; reading assistance origin is unknown.
  Candidate scores partially improve the standard-answer diagnostic, but ALL
  three still assign low generated-class scores to the colloquial AI answer.
  No threshold, winner, population accuracy, calibrated verdict or fusion selected.
- Corrected offline snapshot selection to request only deliberately downloaded
  model/config/tokenizer files, not unrelated images or Git attributes.
- 40 new mechanics tests; full native rerun: 334 passed, no failures/errors/skips,
  clean exit, 11.27 s. Prior concurrent run passed assertions but had an unresolved
  native teardown abort; both reports retained. Docker not rebuilt (205-test image).
- Latest private run3 repeated prior successful scores exactly, with all source
  hashes unchanged. Raw content, weights and detailed outputs remain Git-ignored.
  No interview-content upload, production change, commit, push or PR.

2026-10-08 Beemo external paired-text stress test
- Downloaded pinned public Beemo parquet (8,345,056 bytes, 2,187 distinct prompt
  groups). Before scoring, fixed seed 20261008 and equal five-category quotas:
  200 groups, each with human / original-AI / expert-edited-AI variants.
- Reused pinned HC3, MAGE and SuperAnnotate locally with verified score direction.
  Full raw answers, boundary whitespace only; no ASR, LLM cleanup, truncation,
  training, threshold changes, model winner or fusion. No labels/prompts enter models.
- Completed 1,800 rows: 1,191 scored, 609 abstained, 0 inference errors; all input
  hashes unchanged. Same 90 complete groups used for both contrasts/all models.
- AUROC original/edited: HC3 0.7019/0.5067; MAGE 0.7451/0.6184;
  SuperAnnotate 0.6928/0.6232. All six cross-checked with scikit-learn; paired
  prompt bootstrap CIs retained. AUROC is not accuracy or an AI-use probability.
- Coverage: human 110/200, original AI 151/200, expert-edited AI 136/200 per model.
  Common set is 45% of selected groups; just 2 Closed QA groups survive. No excluded
  cases replaced. Written editing is not spoken personalization; overlap unknown.
- Added 35 mechanics tests. Full suite 369 passed, 0 failures/errors/skips, clean
  exit in 16.42 s after isolating heavy encoder/head parity assertions in a checked
  subprocess. Earlier assertion-passing native teardown abort remains documented;
  root cause unproven. Docker not rebuilt (205-test image).
- Lightweight aggregate report: reports/beemo/paired-text-20261008.md.
  Raw public text, manifest, per-example results and cached weights remain ignored.
  No personal content upload, production change, commit, push or PR.

2026-10-08 Fixed-input detector follow-up
- Added a separate offline `detector-followup` CLI, reviewed source hash pins and
  optional `text-cleanup` dependencies. Original results/manifest remain untouched.
- Completed publisher cleanup comparison: 1,200 rows, 0 errors, original 90 complete
  groups all retained. MAGE softmax original/edited AUROC 0.7551/0.6304; publisher
  AI-logit ranking 0.7581/0.6290. SuperAnnotate cleanup 0.6985/0.6378. Small descriptive
  changes, not a validated solution to edited-text detection. All 14 AUROCs checked.
- Official whole-module cleanup and restricted wrappers agree for every one of
  600 inputs per publisher. Current checkpoint/runtime retained, not old full-stack
  deployment parity. All input/result/source hashes unchanged.
- Implemented Fast-DetectGPT analytic criterion with numerical guards and formula
  parity test. Public smaller GPT-Neo 2.7B cache downloaded (~10.7 GB), SHA verified,
  complete active-weight loading and repeated public-text smoke test passed on MPS.
  Full batch completed: 600 rows, 397 scored, 203 length abstentions, 0 errors.
  Exact same 90 groups as cleanup run; original/edited AUROC **0.8535/0.6116**,
  all metrics cross-checked. Original ranking improves, edited-text weakness remains.
  NOT the recommended Llama3 pair; no cloud provisioning. No model selected.
- 22 added tests; final full native suite **391 passed**, clean exit, 16.69 s. Core/Docker
  dependencies unchanged; Docker image remains at 205 tests. No production scoring,
  interview upload, training, threshold selection, commit, push or PR.
- Lightweight report: reports/beemo/detector-followup-20261008.md;
  protocol: docs/detector-followup.md. Raw content and cached weights remain ignored.

2026-10-08 Verbatim audio/ASR pilot mechanics and partial diagnostic
- Local MVP research narrows the primary test to AI-verbatim vs independent
  spontaneous/self-scripted speech, not reading detection or all AI assistance.
  Client-wide policy unchanged; personalized AI assistance is excluded, not human.
- Added standalone two-stage `verbatim-pilot`, three-condition input template and
  protocol. Same offline Whisper small CPU-int8 settings; metadata does not enter
  the detector. Frozen source/provenance/transcript integrity and guards enforced.
- Existing two recordings and two known AI pure-text controls processed; fresh ASR
  exactly reproduces old text hashes. First prepare emitted verified files but
  aborted at native teardown (134); new prepare retry exited 0 with identical hashes.
  Native root cause unproven, no forced-exit workaround. Both detector passes exited
  0 and repeat all four statistics exactly; no inference errors or threshold fit.
- At initial scoring, three-condition audio validation was incomplete: reading
  provenance awaited user confirmation (subsequently resolved below); independent self-written reading absent.
  Pure-text controls do not fill these audio conditions. No accuracy/FPR/AUROC claim.
- 27 added tests; full native suite **418 passed**, clean exit, 23.59 s. Core/Docker
  dependencies and backend/scoring API unchanged. No model download, training,
  personal content upload, commit, push or PR; detailed outputs remain ignored.
- Aggregate status: reports/verbatim/pilot-status-20261008.md;
  workflow: docs/verbatim-pilot.md; private detailed output under data/processed.

2026-10-08 User confirmation of existing audio provenance
- User confirms reading the assistant-generated standard answer and independently
  answering in the spontaneous recording. Annotated AI_VERBATIM and human_spontaneous
  with self_reported provenance, not protocol_verified; confirmation followed scoring.
- Added a private provenance-only annotation with original input/manifest/result
  hashes. Original frozen metadata, transcripts and predictions remain unchanged.
  No ASR/inference rerun, training, threshold fitting or model/code changes.
- Spoken AI ranks above independent speech in this one pair; no accuracy, FPR,
  AUROC or correct-classification claim. Human self-written-and-read audio still
  needed; exact original AI script needed for any pre-/post-ASR comparison.
- Aggregate status updated; private annotation stays ignored. No commit or push
  occurred during provenance confirmation.

2026-10-08 Research PR preparation
- Added docs/audio-transcript-research-update.md as a concise handoff with original-AI
  benchmark results, spoken diagnostic limitations and reproduction instructions.
- Preparing a stacked research PR above PR #5; raw media, text, weights, datasets,
  detailed personal outputs and regenerated Michigan features excluded.
- Removed a report sentence that incorrectly presumed every reading source was
  unknown; existing frozen reports unchanged. Regression assertion added.
- Pre-publication native test rerun: 418 passed in 20.43 s, clean exit.
  Evidence: reports/pr5_validation/native-tests-pr-sync-20261008.xml.
- Published research branch and PR #6 targeting feature/docker-stt-staged-readiness.
  Only audited code, templates, docs and lightweight reports pushed; raw/private
  artifacts and regenerated Michigan features remain excluded. No PR merged.
```
