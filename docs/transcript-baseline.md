# Local audio -> transcript -> text-detector baseline

Research prototype, implemented 2026-10-07. This is NOT a validated interview
AI-assistance detector, hiring score, or production STT/model selection.

## What runs

1. Confirm a candidate-only recording, answer interval, or transcript.
2. For audio: normalize to mono 16 kHz PCM, check channel quality, and transcribe
   locally using the existing faster-whisper adapter (`small`, CPU/int8, automatic
   language detection, word timestamps, VAD enabled, no initial prompt).
3. Keep the unedited ASR transcript and timestamps. No LLM rewriting or filler cleanup.
4. Score the complete English answer using the pretrained HC3 RoBERTa baseline.
5. Save private transcript JSON/TXT, result JSON, normalized audio (audio inputs),
   and a readable Markdown report. No raw content is printed to the terminal.

The original ALLSSTAR reading/spontaneous classifiers and the team's core
services, evidence contract, STT benchmark configuration and Docker are unchanged.
This command is deliberately separate from the core pipeline. A full multi-speaker
interview must first be separated into candidate answers; this module does not
perform diarization or infer which speaker is the candidate.

## Install and download

Run from the repository root on a machine with space for approximately 500 MB of
detector weights plus optional Python dependencies and ASR weights if missing.

```bash
.venv/bin/python -m pip install -e '.[text-research,stt-faster-whisper]'
HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
  .venv/bin/transcript-baseline download
```

Detector: [Hello-SimpleAI/chatgpt-detector-roberta](https://huggingface.co/Hello-SimpleAI/chatgpt-detector-roberta).
Pinned revision: `d2b342c61775d5dd0221808a79983ed3b86ffd86`.
The verified class order is `Human=0`, `ChatGPT=1`. The model card describes
training on full answers and sentence splits from HC3; it is a 2023 written-Q&A
baseline, not a model trained on ASR transcripts or contemporary interviews.

The publisher ships PyTorch `.bin` weights rather than safetensors. Loading uses
`weights_only=True`, PyTorch >=2.6, `trust_remote_code=False`, and a fixed revision.
No unrestricted pickle loading or Hub custom code is permitted. Model licensing
is not explicitly declared in the inspected card: clarify permission before
commercial deployment or redistribution. Do not describe public weights as
automatically permitting commercial hiring use.

The ASR adapter does not download weights during prediction. This machine already
has `Systran/faster-whisper-small` revision
`536b0662742c02347bc0e980a01041f333bce120` under `.cache/models/faster-whisper`.
On another machine, explicitly provision its weights through the existing STT
workflow before using the audio command.

## Use with a new recording

```bash
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
  .venv/bin/transcript-baseline predict \
  --audio data/raw/manual_audio/cuda-graph-20261007/speaking.m4a \
  --candidate-only \
  --out-dir data/processed/transcript_demo/speaking-run1
```

Choose a NEW output directory each run: existing outputs are never overwritten.
The CLI only permits output under this checkout's ignored `data/processed/`.
Use `--start 12.5 --end 77.0` to isolate a known candidate-only answer. Timestamps
in the saved transcript are relative to the extracted answer, and the result
records its interval in the original recording. Do not concatenate unrelated
answers, questions or speakers simply to reach the minimum length.

For an already isolated candidate answer in `.txt` or project/Whisper `.json`:

```bash
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
  .venv/bin/transcript-baseline predict \
  --transcript data/processed/private_inputs/answer.txt \
  --language en --candidate-only \
  --out-dir data/processed/transcript_demo/sidecar-run1
```

An untagged sidecar needs an explicit English declaration. A JSON language tag
takes precedence: `zh` cannot be overridden by declaring English. Audio language
is detected rather than forced to English. The model only supports English in
this prototype; automatic language identification itself can be wrong.

## Guards and interpretation

- Empty, unsupported/unknown-language, or <50-word answers receive no score.
  The 50-word cutoff is an engineering guard, NOT an empirically validated threshold.
- Silence, clipping and the existing heuristic noisy-channel flag require quality
  review; ASR and scoring are skipped for flagged audio. These flags do not prove
  that unflagged audio is accurate or free of hallucinations.
- Answers over 512 tokens, including special tokens, receive no score. There is
  no silent truncation, partial-answer scoring, or unvalidated chunk-score averaging.
- `ai_text_score` is the ChatGPT-class softmax output. It is NOT a calibrated
  probability of real-time AI use; no decision threshold or candidate verdict is
  issued. `confidence` and `verdict` remain null.
- Source and transcript SHA-256s, model revision, ASR settings, timings, lengths
  and status are recorded. Expected delivery/assistance labels and filenames do
  not enter the detector. Ground truth remains unknown until independently verified.
- No hosted ASR/detection API, audio upload, transcript upload, training or fusion.

Research cautions: [RAID](https://aclanthology.org/2024.acl-long.674/) documents
domain/model/attack sensitivity; [Liang et al.](https://arxiv.org/abs/2304.02819)
documents non-native-English bias in evaluated text detectors. These studies
do not establish this checkpoint's accuracy on spoken technical interviews.

## Current verification and limitations

- Local safe-weight loading and inference succeeded with networking disabled.
- Two supplied personal recordings completed ASR -> detector inference, with
  113 and 140 words. Both had no channel-quality flags and fit the token capacity.
- Their score ordering was counterintuitive: the user-described spontaneous
  recording scored higher than the reading recording. The ASR also misrecognized
  technical terminology. Preserve the original outputs; do not tune a threshold
  or select another model simply to make these two diagnostic clips look correct.
- Reading/spontaneous descriptions are not verified AI-assistance ground truth.
  The smoke test demonstrates function only, not classification accuracy or cause
  of failure. Human transcript review and independently labeled testing remain open.
- 35 new fake-detector/mechanics tests passed. Entire native suite: 294 passed,
  0 failures/errors/skips in 10.27 s. Docker was not rebuilt (earlier 205-test image).

Private results: `data/processed/manual_audio/cuda-graph-text-20261007/`.
Do not commit recordings, transcripts, model weights, or detailed personal reports.

## Next: four-condition pilot, not retraining on two examples

Use `config/transcript_pilot.template.json` as a planning template, NOT a staged
import manifest. Map collected answers into the existing staged tools separately.

| Condition | AI-assistance label | Purpose |
| --- | --- | --- |
| Familiar-topic spontaneous answer, no AI | HUMAN_UNASSISTED | Fluent legitimate negative control |
| Natural delivery of a self-written script, no AI | HUMAN_UNASSISTED | Separate script use from AI use |
| Natural delivery of an AI-produced answer | AI_VERBATIM | AI-content positive control |
| AI points reorganized in the speaker's own words | AI_PERSONALIZED | More realistic paraphrased assistance |

Collect all four conditions from each consenting participant with comparable
lengths, equipment and topic difficulty. Collect human-only conditions before AI
exposure; use counterbalanced matched questions so seeing an AI answer cannot
contaminate later human controls. Record model/prompt/answer provenance for AI
conditions and keep that content private. All audio must pass through the same
ASR settings. Do not compare clean AI text against noisy human ASR text.

Keep participants and questions separate across any future training/validation/test
sets. Report false positives on BOTH human controls and performance separately for
verbatim vs personalized AI assistance. A small pilot can expose failure modes,
but cannot establish population accuracy, fairness or hiring suitability.
