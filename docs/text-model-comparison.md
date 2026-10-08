# Frozen-transcript detector comparison

Implemented locally on 2026-10-07. Diagnostic research only: this does not select
a production detector, estimate interview accuracy, or provide a hiring verdict.
The audio-delivery model, production pipeline and Docker remain unchanged.

## Candidates and score semantics

| Candidate | Pinned Hugging Face revision | Output used here | Licensing status |
| --- | --- | --- | --- |
| [HC3 RoBERTa](https://huggingface.co/Hello-SimpleAI/chatgpt-detector-roberta) | `d2b342c61775d5dd0221808a79983ed3b86ffd86` | Two-class softmax, class 1 = ChatGPT | Card does not explicitly declare a licence; clarification pending |
| [MAGE](https://huggingface.co/yaful/MAGE) | `0d82ca0fdf6ebef5babb813cc11bd8eb2552c846` | Two-class softmax, class 0 = machine, class 1 = human | Model card declares Apache-2.0 |
| [SuperAnnotate](https://huggingface.co/SuperAnnotate/ai-detector) | `74b2b8580915c202607c09f64f8170eaa87a6a14` | One GENERATED logit, then sigmoid | Weights carry custom SAIPL terms; deployment/redistribution review pending |

MAGE's numeric label mapping is verified from its
[pinned author implementation](https://github.com/yafuly/MAGE/blob/6d11f851184b9f04166f952ddc1f47727f36710f/deployment/utils.py),
not assumed to match HC3. Its publisher deployment uses a class-0 raw-logit
cutoff of 3.08583984375. We retain raw logits but do NOT apply this cutoff or
replace it with a softmax cutoff.

SuperAnnotate requires the author's
[custom classifier architecture](https://github.com/superannotateai/generated_text_detector/blob/dbd6317968d144291192a2baf33e11df4e6cdf65/generated_text_detector/utils/model/roberta_classifier.py):
RoBERTa-large encoder without pooling, first-token representation, dropout, and
a single linear output. It is NOT the standard Hugging Face two-class RoBERTa
head. Our inference-only reconstruction loads the complete safetensors state
strictly, rejects missing classifier weights, and does not execute Hub code.
The tiny encoder config is separately pinned to FacebookAI/roberta-large revision
`722cf37b1afa9454edce342e7895e588b6ff1d59`; no extra encoder weights are downloaded.
The author's source licence and the model-weight licence are distinct.

## Protocol

- Reuse the two existing ASR transcripts and two previously generated transcripts.
  Do not rerun ASR, correct terminology, regenerate, rewrite, or tune on the scores.
- The user-described spontaneous recording is a provisional independent-answer
  control, not independently verified ground truth. Reading describes delivery,
  not verified AI assistance. Its AI-origin label remains unknown.
- BOTH synthetic transcripts are assistant-generated. The colloquial version
  imitates a speaking style and is NOT a real human negative control.
- Freeze candidate-answer text and provenance before model loading. Each model
  receives exactly the same `Transcript.text`, without filenames or labels.
  The existing sidecar loader strips surrounding whitespace; internal words,
  pauses represented in text, punctuation and newlines are not rewritten.
- Use raw checkpoint inference, not exact publisher deployment pipelines:
  publisher-specific Moses/clean-text or Markdown/HTML cleanup is not applied.
  This choice is explicit, not a claim to reproduce published benchmark scores.
- English only, at least 50 words, at most 512 tokens including special tokens
  for every candidate. The minimum is an engineering guard, not a reliability
  guarantee. No truncation or averaging across chunks. MAGE internally pads to
  its attention window; that padding does not delete answer content.
- Model failures and abstentions have null scores, never fabricated zeroes.
  Source/manifest checksums are verified again after inference. Partial results
  remain `integrity_status=pending`; source changes mark them `failed`.
- Scores are uncalibrated and not interchangeable between models. No thresholds,
  model winner, fusion, retraining, accuracy estimate or cheating probability.

## Run locally

Approximately 2 GB of additional candidate weights beyond cached HC3 are needed,
plus optional dependencies and sufficient CPU RAM for RoBERTa-large loading.
Heavy imports are lazy; the core standard-library pipeline does not require them.

```bash
.venv/bin/python -m pip install -e '.[text-research]'
HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
  .venv/bin/transcript-compare download

HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
  .venv/bin/transcript-compare run \
  --manifest data/processed/text_comparison/cuda-graph-20261007/manifest.json \
  --out-dir data/processed/text_comparison/cuda-graph-20261007/new-run
```

Download is a separate explicit public-weight operation. Inference only uses
local files and sends no recording/transcript to hosted inference. The CLI
requires output under this checkout's ignored `data/processed/`; existing output
directories are never overwritten. `python -m
interview_integrity.modeling.text_comparison` is an equivalent entry point.
Use `--models mage superannotate` to omit HC3, without otherwise changing inputs.

The private JSON manifest must contain `candidate_only: true` and a nonempty
`samples` list. Each sample has a unique filesystem-safe `id`, a `.txt` or
project/Whisper `.json` `path` relative to the manifest, optional explicit
`language`, and `provenance` object. A JSON transcript's language tag takes
precedence over a declaration. Unknown language abstains. The consented,
candidate-only answer must already be isolated; this tool does not diarize.

Outputs: frozen input copies, `comparison.json` with revisions, runtime versions,
source/text hashes, statuses, scores, raw logits and timings, plus `report.md`.
Timings are diagnostic, not a latency benchmark: lazy HC3 weight loading is
included in its first inference, and CPU/runtime conditions are not controlled.
Do not commit inputs, personal provenance, model weights or detailed reports.

## Current results and interpretation

The latest private run is
`data/processed/text_comparison/cuda-graph-20261007/run3/`.
All 12 sample-model pairs scored without truncation. All source hashes verified;
scores exactly repeated the earlier successful run. The first run's missing
ancillary-cache-file errors are retained separately, not confused with zero scores.

On these already-inspected examples, MAGE and SuperAnnotate assigned lower
generated-class scores to the user-described spontaneous transcript than HC3,
and higher scores to the standard synthetic answer. HOWEVER, all three assigned
low generated-class scores to the synthetic colloquial answer. Reading cannot be
scored as a correct/incorrect assistance detection because its origin is unknown.
This is evidence of a remaining diagnostic blind spot, not a population accuracy,
false-positive rate, causal explanation, or grounds for selecting a winner.

40 new mechanics tests passed, including class order, sigmoid vs softmax,
strict custom-head loading/eval parity, label isolation, length/language guards,
null failure scores, offline cache selection and checksum failure handling.
The entire native suite passed **334 tests, 0 failures/errors/skips in 11.27 s**,
with a clean process exit on a standalone rerun. An earlier concurrent run also
passed all assertions but had a native-library teardown abort (exit 134);
its cause is not established. Both JUnit reports are preserved. Docker was not
rebuilt and remains at the earlier 205-test image. Tests establish software
mechanics, NOT detector performance.

Next validation should use independently collected candidate answers across the
four conditions in `config/transcript_pilot.template.json`, with identical ASR
settings for all conditions and participant/question separation. Keep fluent
human answers and self-written scripts as negative controls, and evaluate
AI-verbatim and AI-personalized answers separately. Do not fit thresholds or
fine-tune on these four diagnostic samples.
