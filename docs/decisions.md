# Pending Decisions

Substantial choices the team still has to make. The code is structured so that each one
can be plugged in behind an existing interface without changes elsewhere.

## D1. Speech-to-text provider (interface: `transcription.base.Transcriber`)

> Superseded by the fuller comparison in [stt-decision.md](stt-decision.md). Still pending approval.

Currently only `SidecarTranscriber` is implemented. It loads existing JSON/TXT transcripts
(Whisper-style JSON is supported).

| Option | Pros | Cons |
|---|---|---|
| **faster-whisper (local, e.g. `small`/`medium`)** | Free; audio never leaves the machine (privacy/IRB-friendly); word timestamps; reproducible | Needs CPU/GPU time; tends to drop disfluencies ("um", "uh") by default, which weakens filler features |
| **WhisperX (local)** | Whisper + forced alignment → more accurate word timestamps; optional diarization (pyannote) to separate interviewer and candidate | Heavier install (PyTorch, HF token for diarization) |
| **Hosted API (Deepgram / AssemblyAI / OpenAI)** | Fast, accurate, built-in diarization; some keep filler words | Cost; sends candidate audio to a third party (consent and data-policy implications); vendor lock-in |

Recommendation: faster-whisper locally to start (privacy, cost), with WhisperX as the
upgrade path if timing precision or diarization becomes the bottleneck. For
disfluency-sensitive experiments, keep a manually corrected transcript subset as a reference.

## D2. Processed data format

Current: `samples.jsonl` (canonical) + `samples.csv` (flat export). Standard library only.

| Option | Pros | Cons |
|---|---|---|
| JSONL + CSV (current) | No dependencies; human-readable; git-diffable; JSONL keeps nulls/nesting | Slow and large at scale; CSV loses types (null vs "") |
| Parquet | Typed, compressed, fast with pandas/polars | Needs pyarrow; not human-readable |

Recommendation: keep JSONL as the source of truth for now and add a Parquet export once
the dataset passes a few thousand rows or we add high-dimensional features (embeddings).

## D3. Question-answer semantic similarity (interface: `features.linguistic.SimilarityScorer`)

Currently `null`. `qa_content_word_overlap` provides a lexical-only baseline.
Options: sentence-transformers (local, e.g. `all-MiniLM-L6-v2`), a hosted embedding API,
or an LLM-judge via OpenRouter. This needs a team decision.

## D4. Baseline model and scoring formula

Not started. This needs labeled staged data first. Likely candidates: logistic regression or
gradient-boosted trees on the explainable features, with per-feature contributions to
support the "likelihood/confidence score" explanation. This needs a team decision.

## D5. Speaker separation

Energy VAD cannot tell the interviewer and candidate apart. Options: record separate
audio tracks per speaker (simplest for staged data), annotate answer windows in metadata
(current approach), or diarization (WhisperX/pyannote).

## D6. Google Drive access backend (interface: `storage.remote.RemoteStorage`)

`LocalFolderStorage` works today with any mounted folder. Choose how teammates and scripts
reach Drive:

| Option | Pros | Cons |
|---|---|---|
| **rclone remote** (`rclone config` → Drive, OAuth in browser) | CLI-friendly; `rcat` streams uploads with no temp files; each teammate authorizes their own account | CMU Workspace may block rclone's shared OAuth client, so we might need our own GCP client ID |
| **Google Drive for Desktop** (streaming mode) + `LocalFolderStorage` | Zero code; works now | The app manages its own cache (hard to bound); uploads still pass through the laptop; not usable in Colab/CI |
| **Drive API** (Python client, OAuth or service account) | Fully programmatic; file IDs in `remote_reference`; works in Colab | Adds dependencies and a GCP project; a service account needs a Shared Drive |

Also decide: **My Drive vs a CMU Shared Drive** for the root folder. A Shared Drive is
recommended so the team, not one student account, owns the data.

Recommendation: rclone backend plus a CMU Shared Drive.

## D7. Numeric dependency for pitch/prosody features

Pitch (F0) features need a numeric library; pure Python is too slow. This is not an ML
model choice. Options: **numpy** (implement YIN; smallest dependency), **Praat-parselmouth**
(standard phonetics tool; GPL-licensed Praat underneath), or **librosa** (`pyin`; pulls in
numpy/scipy/numba). Recommendation: numpy, if pitch features are approved. See
[audio-features.md](audio-features.md).
