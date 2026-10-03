# AI Interview Integrity Capstone

CMU capstone project: **AI-Powered Interview Integrity Monitoring Platform**.

## Objective

This prototype identifies **signals of possible real-time AI assistance** during virtual
interviews. The intended output is an explainable **AI-assistance likelihood / confidence
score** that helps a human interviewer decide whether further investigation or follow-up
questioning is appropriate.

The system does **not** determine that a candidate is cheating, and it must not be used
for automated candidate rejection.

## Current MVP scope

In scope (this milestone: data ingestion and feature-extraction foundation):

```text
Interview video → ingestion → audio extraction → transcript → question/answer windows
    → linguistic features + timing/audio features → structured dataset row → (baseline experiments)
```

Out of scope for now: deepfake detection, gaze tracking, face recognition, automated
rejection, production deployment, Teams/Zoom integration, and the detection model itself.

## Dataset strategy (summary)

- **Staged mock interviews** are the eventual primary ground truth. Each answer is labeled
  by how it was actually produced: `HUMAN_UNASSISTED`, `AI_ASSISTED`, `AI_VERBATIM`,
  `AI_PERSONALIZED` (or `UNKNOWN`).
- **Public deception datasets** (DOLOS, Real-life Deception, Bag-of-Lies) are supporting
  data only. Their labels go in `deception_label`. They are **never** converted into
  AI-assistance labels, and the schema enforces this.
- **Augmented variants** of a recording stay in the same train/val/test partition as the
  original (splits are grouped by participant).

Full details: [docs/data-strategy.md](docs/data-strategy.md).

## Data storage

**Public datasets are processed straight from their official source.**
`interview-integrity process-source` streams one clip at a time into a temporary cache,
extracts features, and deletes the clip. Only the lightweight outputs are committed, in
[processed/](processed/). No raw video is stored in Git, Drive or on laptops.

```bash
interview-integrity process-source --dataset michigan_deception   # outputs → processed/
```

Optional shared storage: raw datasets can also live in **Google Drive**
(`AI Interview Integrity Capstone/`), not in Git and not permanently on laptops. The repo tracks only manifests
(`manifests/datasets.json`, `manifests/files/*.csv`) that say where each file lives.
Processing pulls one file at a time into a temporary cache capped at 500 MB, uploads the
lightweight outputs back to Drive, and deletes the local copy. See
[docs/data-storage.md](docs/data-storage.md).

```bash
interview-integrity datasets status
interview-integrity storage-init --root "<shared root>"
interview-integrity datasets acquire michigan_deception --root "<shared root>" --limit 5
interview-integrity process-remote --dataset michigan_deception --root "<shared root>" --limit 5
```

| Dataset | Access | Status |
|---|---|---|
| UMich Real-life Deception | Public | **Processed: 121 clips → [processed/](processed/)** |
| DOLOS | ROSE Lab Release Agreement | Waiting on manual request |
| Bag-of-Lies | Institution-signed license | Waiting on manual request |
| Staged interviews | Team-recorded | Not collected yet |
 Open choices:
[docs/decisions.md](docs/decisions.md).

## Documentation

- [docs/architecture.md](docs/architecture.md): what's implemented vs planned, modules, where data lives, how features plug in
- [docs/teammate-validation.md](docs/teammate-validation.md): exact commands for heavy checks (Docker build, STT benchmark, full dataset runs)
- [docs/docker.md](docs/docker.md): container usage and safe disk cleanup
- [docs/evidence-contract.md](docs/evidence-contract.md): shape of future reviewable signals (no scoring)
- [docs/audio-features.md](docs/audio-features.md): audio/timing feature inventory and expansion plan
- [docs/staged-interviews.md](docs/staged-interviews.md): staged-interview protocol, metadata and pilot workflow
- [docs/stt-decision.md](docs/stt-decision.md): **pending** speech-to-text decision
- [docs/data-strategy.md](docs/data-strategy.md), [docs/data-storage.md](docs/data-storage.md), [docs/decisions.md](docs/decisions.md)

## Repository layout

```text
src/interview_integrity/
  ingestion/      video probing, checksums, ingest manifest
  audio/          audio extraction (ffmpeg → 16 kHz mono WAV), energy-based VAD
  transcription/  provider-agnostic Transcriber interface + sidecar transcript loader
  features/       linguistic and timing features
  datasets/       schema (InterviewSample), JSONL/CSV I/O, group-aware splits
  llm/            provider-agnostic LLM interface (OpenRouter placeholder)
  storage/        shared-storage backends, bounded temp cache, manifests, dataset acquisition
  pipeline.py     end-to-end processing of one video
  cli.py          `interview-integrity` command
manifests/      dataset registry + per-file manifests (no media)
data/{raw,interim,processed}/   local data only, gitignored
docs/  examples/  notebooks/  tests/
```

## Setup

Requirements: Python ≥ 3.10 and **ffmpeg** (`brew install ffmpeg` / `sudo apt install ffmpeg`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # only needed later for OpenRouter; never commit .env
pytest                        # media fixtures are generated with ffmpeg at test time
```

The runtime package uses only the Python standard library plus the ffmpeg binaries.

## Docker (optional)

```bash
docker compose build
docker compose run --rm app pytest
docker compose run --rm app interview-integrity --help
```

The image holds code, Python dependencies and ffmpeg only; data is bind-mounted. See
[docs/docker.md](docs/docker.md). It hasn't been built on the development laptop
(disk constraints); see [docs/teammate-validation.md](docs/teammate-validation.md).

## Commands at a glance

| Command | Purpose |
|---|---|
| `process` / `process-batch` | one recording / a folder of `<name>.metadata.json` + video |
| `process-remote` / `process-source` | from shared storage / streamed from an official public archive |
| `staged template` / `import-labels` / `validate` | prepare staged-interview metadata |
| `quality` | dataset quality report (exit 1 on errors) |
| `split` | leakage-safe train/val/test splits |
| `stt-list` / `stt-eval` / `stt-benchmark` | STT candidates and evaluation (no provider chosen) |
| `datasets status` / `build-manifest` / `acquire` | dataset registry and acquisition |
| `storage-init` / `cache-clean` | shared folder layout / remove stale temp caches |

## Process one sample video

1. Put the video somewhere local (e.g. `data/raw/staged/INT001.mp4`). Do not commit it.
2. Write a metadata JSON (see [examples/](examples/)):

   ```json
   {
     "interview_id": "INT001",
     "participant_id": "P001",
     "source_dataset": "staged",
     "question_id": "Q01",
     "question_text": "Why does software testing matter?",
     "assistance_label": "HUMAN_UNASSISTED"
   }
   ```

   For videos containing several answers, use a `questions` list with `answer_start` /
   `answer_end` (seconds) for each one. Add `question_end` to enable response latency.

3. Run:

   ```bash
   interview-integrity process \
     --video data/raw/staged/INT001.mp4 \
     --metadata examples/sample_metadata.json \
     --transcript path/to/transcript.json   # optional; .json (Whisper-style) or .txt
   ```

Outputs:
- `data/interim/INT001/`: `audio.wav`, `transcript.json`, and `ingest.json` (video info,
  SHA-256, and audio metadata such as duration, sample rate and channels)
- `data/processed/samples.jsonl`: canonical dataset. Re-processing the same answer
  replaces its row instead of duplicating it.
- `data/processed/samples.csv`: flat export for spreadsheets and pandas

Then assign leakage-safe splits:

```bash
interview-integrity split --input data/processed/samples.jsonl   # grouped by participant_id
```

Example row (abridged):

```json
{
  "interview_id": "INT001", "participant_id": "P001", "question_id": "Q01",
  "source_dataset": "staged", "assistance_label": "HUMAN_UNASSISTED", "deception_label": "UNKNOWN",
  "transcript": "Um, I think I think testing matters. You know, it catches bugs early.",
  "answer_start": 0.5, "answer_end": 3.5, "answer_duration": 3.0, "response_latency": null,
  "word_count": 13, "filler_word_count": 2, "speech_rate_wpm": 260.0, "pause_count": 1,
  "timing_source": "word_timestamps"
}
```

## Features (all explainable, all nullable)

| Group | Features |
|---|---|
| Linguistic | `word_count`, `sentence_count`, `avg_sentence_length`, `type_token_ratio`, `mattr`, `filler_word_count`, `filler_rate_per_100_words`, `discourse_marker_count`, `repetition_count`, `self_correction_count`, `qa_content_word_overlap`, `qa_semantic_similarity` (interface only, null for now) |
| Timing | `answer_duration`, `response_latency`, `speech_duration`, `silence_duration`, `pause_count`, `long_pause_count`, `mean/max/total_pause_duration`, `pause_duration_std`, `pause_ratio`, `speech_segment_count`, `mean_speech_segment_duration`, `speech_segment_duration_std`, `speech_rate_wpm`, `articulation_rate_wpm`, `speech_rate_cv` (needs word timestamps) |
| Loudness | `speech_level_mean_dbfs`, `speech_level_std_db`, `speech_level_range_db` |
| Recording quality | `audio_noise_floor_dbfs`, `audio_speech_level_dbfs`, `audio_snr_db`, `audio_peak_dbfs`, `audio_clipping_ratio`, `audio_is_silent`, `audio_is_noisy`, `audio_is_clipped` |
| Provenance | `timing_source` (`word_timestamps` or `energy_vad`), `transcript_source`, `video_reference`, `video_sha256` |

All times are in seconds. Values that cannot be measured are `null`, never guessed.
Definitions and limitations: [docs/audio-features.md](docs/audio-features.md). Check a
dataset with `interview-integrity quality --input <samples.jsonl | dir>`.

Staged interviews add `question_start`, `ai_model_used`, `ai_prompt_used`,
`generated_ai_answer` and `response_notes` (all optional). See
[docs/staged-interviews.md](docs/staged-interviews.md).

## Current limitations

- **No speech-to-text engine yet.** Transcripts must be supplied as files. Use
  `interview-integrity stt-eval` to compare candidates against reference transcripts. The provider
  choice is pending ([docs/decisions.md](docs/decisions.md#d1-speech-to-text-provider-interface-transcriptionbasetranscriber)).
  Without a transcript, linguistic features are `null` and timing comes from VAD.
- **Energy VAD is crude.** Its threshold adapts to each recording's level, and flat noise
  isn't reported as speech, but loud background noise can still count as speech. It
  cannot separate the interviewer from the candidate: give `question_end` or answer
  windows for mixed-speaker audio. Noisy or clipped recordings are flagged by the
  quality report.
- **Filler counts depend on the transcript source.** Many ASR models remove "um"/"uh".
- **Self-correction detection is heuristic** (repeats and repair phrases like "sorry",
  "I meant").
- **Response latency needs `question_end`** in the metadata. Otherwise it is `null`.
- No visual features, augmentation transforms, semantic similarity model, or detection
  model yet.
- The OpenRouter client is a configuration-only placeholder.
- No native Google Drive backend yet (decision D6). Shared storage currently works through a
  mounted folder, such as Drive for Desktop.
- The Michigan dataset has no speaker IDs, so each clip is treated as its own participant
  (`unknown:<video_id>`). Participant-grouped splits can't guarantee no speaker overlap
  until speakers are annotated.
