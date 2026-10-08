# Verbatim AI answer: local audio/ASR pilot

Research scope agreed in this chat: initially examine substantially verbatim AI
answers in interview transcripts, **not all AI assistance and not reading detection**.
This is not a client-approved change to the overall assistance policy or a
production hiring model. Personalized assistance remains AI assistance; it is
outside this pilot's main evaluation, never a human negative.

## Three primary audio conditions

| Condition | Meaning | Assistance target |
| --- | --- | --- |
| `human_spontaneous` | Independent familiar-topic response, including fluent delivery | Negative |
| `human_self_script` | Independently written without AI, then read naturally | Negative, reading confound control |
| `ai_verbatim` | Substantially unchanged AI-produced answer spoken naturally | Positive |

Use the [input template](../config/verbatim_pilot.template.json) in private ignored
storage. Labels are metadata, **not detector inputs**. `self_reported` and
`protocol_verified` are distinct; do not assert controlled verification for personal
recordings just because a participant confirms their origin.

Keep exact AI prompt/model/output and any independent human script privately.
Generated written controls may be added as `input_kind=text`,
`condition=ai_text_control`, `provenance_status=known_generated`, but they do not
fill a primary audio condition. They cannot measure ASR effects on another answer.
An unknown reading source uses `condition=unknown`, `provenance_status=unknown`.

For a new recording: approximately 60–90 seconds of English is useful for this
engineering pilot, not a validated scientific duration. Match recording setup,
domain and answer length as far as possible. Record independent human conditions
before exposure to AI answers. Avoid reading an assistant-provided script for the
human-self-script condition. The existing CUDA examples are previously inspected,
so they remain diagnostic rather than a blind controlled trial. Follow consent,
privacy and retention requirements before recruiting new participants.

## Implementation

The separate optional `verbatim-pilot` CLI has two stages:

1. `prepare`: validate provenance and candidate-only input; normalize audio locally
   with ffmpeg to 16 kHz mono PCM; apply audio-quality guards; transcribe with the
   same faster-whisper small / CPU int8 / automatic language detection / VAD on /
   beam 5 / word timestamps on / **no initial prompt**. No downloads. Text controls
   bypass ASR and remain explicitly separate. Freeze all source, metadata,
   transcript-file and transcript-text hashes before detector inference.
2. `score`: a separate process loads cached pinned GPT-Neo 2.7B and the existing
   Fast-DetectGPT implementation. Pass only unedited transcript text to the detector.
   English-only, minimum 50 words, maximum 512 tokens, no truncation. Preserve null
   scores for empty/short/unsupported/quality-flagged inputs; errors are not human
   predictions. Recheck frozen source/provenance/transcript hashes afterward.

The signed statistic may be negative; **larger means more machine-like under the
method**. Zero, 0.5 and 1 are not approved decision thresholds. No probability
mapping, binary verdict, fitted threshold, accuracy/FPR/AUROC estimate, training,
fusion or production API change. Report missing primary audio conditions explicitly.
Same-speaker/topic diagnostics cannot establish generalization even with all three
conditions present. Larger participant/question-separated pilots are needed before
choosing an operating threshold or reporting low-FPR sensitivity.

Preparation/ASR and detector inference use separate processes to limit native-library
mixing. This does not prove that the intermittent local native teardown issue is fixed.

## Reproduce

Install existing optional `stt-faster-whisper` and `text-research` dependencies;
Whisper small and GPT-Neo weights must already be cached. No new model downloaded
for the executed pilot. Keep private outputs in `data/processed`.

```sh
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
.venv/bin/python -m interview_integrity.modeling.verbatim_pilot prepare \
  --inputs data/processed/verbatim_pilot/my-pilot/inputs.json \
  --out-dir data/processed/verbatim_pilot/my-pilot/prepared

HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
.venv/bin/python -m interview_integrity.modeling.verbatim_pilot score --device mps \
  --manifest data/processed/verbatim_pilot/my-pilot/prepared/manifest.json \
  --out-dir data/processed/verbatim_pilot/my-pilot/scored
```

Existing output directories are not overwritten. Confirming unknown provenance
requires a new input/protocol snapshot, not relabeling frozen results in place.
Do not upload audio, scripts, transcripts, source metadata or detailed per-sample
results to Git. See the [aggregate execution status](../reports/verbatim/pilot-status-20261008.md).
