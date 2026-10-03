# Architecture

A research pipeline that turns interview recordings into explainable, labelled feature
rows for human review. It does **not** decide whether anyone cheated.

```text
recording ─▶ ingestion ─┬─▶ audio pipeline ─────────▶ audio features ─────┐
            (checksum,   │   (extract, validate, VAD)                       │
             metadata)   ├─▶ transcript (Transcriber) ─▶ linguistic features ├─▶ validated rows ─▶ quality report
                         └─▶ [video pipeline: planned] ─▶ [visual_* plug-ins]┘        │
                                                                                      ▼
                                              evidence contract (EvidenceSignal) ─▶ [fusion/scoring: planned]
                                                                                      ▼
                                                                    [human-review output: planned]
```

## Implemented now

| Component | Where | Notes |
|---|---|---|
| Data/video ingestion | `ingestion/` | probe, SHA-256, audio extraction (atomic, cached per source file), `ingest.json` |
| Audio processing | `audio/` | 16 kHz mono WAV, frame levels, adaptive VAD, audio validation (empty/silent/noisy/clipped) |
| Transcription interface | `transcription/` | `Transcriber` + transcript loader; candidate adapters (faster-whisper, WhisperX: lazy, not installed); hosted placeholder (blocked without approval); registry; `stt-eval`, `stt-benchmark` |
| Feature extraction | `features/` | linguistic, timing, loudness, recording quality; `registry.py` (modality + behavioral/quality/provenance); `base.py` plug-in interface |
| Dataset validation | `datasets/` | schema incl. staged-interview fields, atomic JSONL/CSV I/O, leakage-safe splits |
| Quality reporting | `datasets/quality.py` | errors/warnings per row and dataset; `quality` command |
| Staged tooling | `staged.py` | metadata templates, TSV label import, protocol validation |
| Remote-data workflow | `storage/` | storage interface, bounded temp cache (+ stale cleanup), manifests, source-archive streaming |
| Evidence contract | `evidence.py` | signal shape + per-modality quality status; no scoring |
| Application layer | `services.py` | every operation as a function returning structured results; `cli.py` is a thin wrapper |
| Configuration | `config.py` | `INTERVIEW_INTEGRITY_*` environment variables |
| Docker scaffolding | `Dockerfile`, `compose.yaml` | single app container, bind mounts only; not yet built (see [teammate-validation.md](teammate-validation.md)) |

## Planned / unresolved (not implemented)

| Component | Status |
|---|---|
| Final STT implementation | candidates scaffolded; choice pending ([stt-decision.md](stt-decision.md)) |
| Video feature pipeline | shared team work; only the plug-in interface exists; no visual model chosen |
| Model / fusion / scoring layer | not started; no algorithm, fusion method, thresholds or score chosen |
| Review UI | not started |
| API layer | not started; no framework chosen; `services.py` is the intended entry point |
| Database | none; files (JSONL/CSV/JSON) only |
| Production deployment / cloud | none |

## Module boundaries

`audio/`, `features/`, `transcription/` and `datasets/` know nothing about storage or
the CLI. `pipeline.py` orchestrates one recording. `storage/` and `services.py` sit on
top. The runtime uses only the standard library plus ffmpeg/curl. STT packages are
optional extras.

## Where data lives

| What | Where | In Git? |
|---|---|---|
| Public raw video (Michigan) | official source; streamed one clip at a time | No |
| Restricted raw video (DOLOS, Bag-of-Lies, after approval) | shared storage `datasets/<name>/` | No |
| Staged recordings, metadata, transcripts, outputs | private shared storage | **Never** |
| Manifests (where files live, status) | `manifests/` | Yes |
| Temporary working files | temp dir (≤ 500 MB), deleted after each recording; `cache-clean` for leftovers | No |
| Local outputs | `data/` | No |
| Public-dataset features + quality reports | `processed/` | Yes |

## Processing one interview

```bash
interview-integrity process --video rec.mp4 --metadata rec.metadata.json [--transcript rec.transcript.json]
interview-integrity process-batch --dir pilot/            # many recordings, failures don't stop the batch
interview-integrity process-remote --dataset staged_interviews --root "<shared root>"
interview-integrity process-source --dataset michigan_deception   # public archive, no Drive
interview-integrity quality --input data/processed/samples.jsonl
```

For each question, the pipeline:
1. Rejects timestamps outside the recording.
2. Sets the answer window (`answer_start..answer_end`, else search from `question_end`).
3. Finds speech intervals (word timestamps, else adaptive VAD).
4. Computes features: unknown values are `null`; quality fields are kept separate from
   behavioral ones.
5. Runs optional plug-in extractors.
6. Validates the row against the schema.
7. Runs the quality checks.

## Adding features (audio, linguistic, visual, other)

Implement `features.base.FeatureExtractor` (`name`, `prefix`, `extract(ctx) -> dict`) and
pass it via `PipelineConfig(extractors=[...])`. Prefixes: `visual_` (behavioral visual),
`quality_` (quality metadata, never evidence) or `ext_` (other). The pipeline rejects
collisions with core or other plug-in features, and any non-scalar values. Register core
features in `features/registry.py`. Visual contributors: see
[features/visual/README.md](../src/interview_integrity/features/visual/README.md).

## Related docs

[audio-features.md](audio-features.md) · [staged-interviews.md](staged-interviews.md) ·
[evidence-contract.md](evidence-contract.md) · [stt-decision.md](stt-decision.md) ·
[docker.md](docker.md) · [teammate-validation.md](teammate-validation.md) ·
[data-strategy.md](data-strategy.md) · [data-storage.md](data-storage.md) · [decisions.md](decisions.md)
