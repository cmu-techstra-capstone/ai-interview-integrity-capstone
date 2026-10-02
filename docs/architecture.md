# Architecture

A research pipeline that turns interview recordings into explainable, labelled feature
rows. It does **not** decide whether anyone cheated, and no detection model exists yet.

```text
video ──▶ ingestion ──▶ audio extraction ──▶ audio validation ──▶ transcript (optional)
          (probe,       (16 kHz mono WAV,    (empty → error;       (Transcriber interface;
           SHA-256,      atomic, cached       silent/noisy/clipped   STT provider pending)
           metadata)     per source file)     flags)
                                   │
                                   ▼
              per question: answer window ──▶ speech intervals ──▶ features
              (metadata, or search after      (word timestamps,    linguistic · timing ·
               question_end)                   else adaptive VAD)   loudness · recording quality
                                                                    · plug-in extractors (visual, later)
                                   │
                                   ▼
                      validated InterviewSample rows ──▶ quality report ──▶ JSONL / CSV / JSON
```

## Modules (`src/interview_integrity/`)

| Module | Responsibility | Depends on |
|---|---|---|
| `media.py` | ffmpeg/ffprobe wrappers and errors | ffmpeg binaries |
| `ingestion/` | validate video, checksum, extract and validate audio, write `ingest.json` | `audio`, `datasets.schema` |
| `audio/` | extraction, frame levels, adaptive VAD, audio quality | stdlib |
| `transcription/` | `Transcriber` interface, transcript loader, STT evaluation | `features.linguistic` (tokenizer only) |
| `features/` | linguistic, timing, loudness; `base.py` plug-in interface; `visual/` (empty, shared) | `audio`, `transcription` types |
| `datasets/` | schema, JSONL/CSV I/O, group splits, quality checks | — |
| `storage/` | storage backends, bounded temp cache, manifests, dataset sources, remote workflow | `pipeline` |
| `pipeline.py` | orchestrates one recording | all of the above |
| `cli.py` | `interview-integrity` commands | all of the above |
| `llm/` | provider-agnostic LLM interface (placeholder) | — |

Rules: nothing in `audio/`, `features/` or `datasets/` knows about storage. Storage knows
about the pipeline, not the other way round. The runtime uses only the standard library
plus ffmpeg.

## Where data lives

| What | Where | In Git? |
|---|---|---|
| Public raw video (Michigan) | the official source; streamed one clip at a time | No |
| Restricted raw video (DOLOS, Bag-of-Lies, after approval) | shared storage (Drive) under `datasets/<name>/` | No |
| Staged interview recordings | private shared storage (Drive/Box) under `datasets/staged_interviews/` | **Never** |
| Recording metadata (labels, timestamps, AI metadata) | shared storage `metadata/…`, referenced from the manifest | Not for staged data (contains participant content) |
| Manifests (where each file lives, status) | `manifests/` | Yes |
| Temporary working files | system temp dir, ≤ 500 MB, deleted after each recording | No |
| Local pipeline outputs | `data/interim`, `data/processed` | No (gitignored) |
| Public-dataset features and quality reports | `processed/` | Yes |

## How one interview is processed

**Local file:**

```bash
interview-integrity process --video rec.mp4 --metadata rec.json [--transcript rec.json]
interview-integrity quality --input data/processed/samples.jsonl
```

**From storage (manifest row → temp cache → outputs → cache deleted):**

```bash
interview-integrity process-remote --dataset staged_interviews --root "<shared root>"
interview-integrity process-source --dataset michigan_deception    # public archive, no Drive
```

The steps, for each question in the metadata:
1. The answer window is `answer_start..answer_end`. If those are missing, the pipeline
   searches from `question_end` (or 0) to the end.
2. Speech intervals come from word timestamps when the transcript has them, otherwise
   from adaptive energy VAD.
3. Features are computed. Anything that can't be measured is `null`.
4. The row is validated against the schema: labels, time order, and label separation.
5. The quality checks flag problems as errors or warnings
   ([datasets/quality.py](../src/interview_integrity/datasets/quality.py)).

## Adding future visual features

Implement `features.base.FeatureExtractor` (`name`, `prefix="visual_"`,
`extract(ctx) -> dict`) in `features/visual/`. Then pass it in
`PipelineConfig(extractors=[...])`. The pipeline gives it the video path, the answer
window, the transcript and the speech intervals. It rejects feature names without the
prefix or that collide with existing ones. No visual model has been chosen; see
[features/visual/README.md](../src/interview_integrity/features/visual/README.md).

## Related docs

- [audio-features.md](audio-features.md): feature inventory and expansion plan
- [staged-interviews.md](staged-interviews.md): how staged recordings enter the pipeline
- [stt-decision.md](stt-decision.md): pending speech-to-text decision
- [data-strategy.md](data-strategy.md), [data-storage.md](data-storage.md), [decisions.md](decisions.md)
