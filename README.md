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

Full details: [docs/data-strategy.md](docs/data-strategy.md). Open choices:
[docs/decisions.md](docs/decisions.md).

## Repository layout

```text
src/interview_integrity/
  ingestion/      video probing, checksums, ingest manifest
  audio/          audio extraction (ffmpeg → 16 kHz mono WAV), energy-based VAD
  transcription/  provider-agnostic Transcriber interface + sidecar transcript loader
  features/       linguistic and timing features
  datasets/       schema (InterviewSample), JSONL/CSV I/O, group-aware splits
  llm/            provider-agnostic LLM interface (OpenRouter placeholder)
  pipeline.py     end-to-end processing of one video
  cli.py          `interview-integrity` command
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
pytest                        # 62 tests; media fixtures are generated with ffmpeg
```

The runtime package uses only the Python standard library plus the ffmpeg binaries.

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
| Timing | `answer_duration`, `response_latency`, `speech_duration`, `pause_count`, `mean_pause_duration`, `max_pause_duration`, `total_pause_duration`, `pause_ratio`, `speech_rate_wpm`, `articulation_rate_wpm` |
| Provenance | `timing_source` (`word_timestamps` or `energy_vad`), `transcript_source` |

All times are in seconds. Values that cannot be measured are `null`, never guessed.

## Current limitations

- **No speech-to-text engine yet.** Transcripts must be supplied as files. The provider
  choice is pending ([docs/decisions.md](docs/decisions.md#d1-speech-to-text-provider-interface-transcriptionbasetranscriber)).
  Without a transcript, linguistic features are `null` and timing comes from VAD.
- **Energy VAD is crude.** It uses a fixed dBFS threshold and cannot separate the
  interviewer from the candidate. Use metadata answer windows for mixed-speaker audio.
- **Filler counts depend on the transcript source.** Many ASR models remove "um"/"uh".
- **Self-correction detection is heuristic** (repeats and repair phrases like "sorry",
  "I meant").
- **Response latency needs `question_end`** in the metadata. Otherwise it is `null`.
- No visual features, augmentation transforms, semantic similarity model, or detection
  model yet.
- The OpenRouter client is a configuration-only placeholder.
