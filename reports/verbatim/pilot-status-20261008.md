# Verbatim-ASR pilot: execution status — 2026-10-08

Lightweight status only. No raw audio, transcript text, participant identity,
independent scripts or detailed individual predictions are included here.

## What ran

- Two existing user-provided English recordings, same familiar technical topic,
  plus two previously assistant-generated pure-text controls. No new participants,
  synthetic voices, hosted inference, model downloads or training.
- The user confirmed on 2026-10-08 that the spontaneous recording is independent
  and the reading recording uses the assistant-generated standard answer. They
  can therefore be annotated **human_spontaneous / AI_VERBATIM**, respectively,
  with **self_reported**, not independently protocol-verified, provenance.
  Confirmation arrived after scoring; this is not blind validation. The initial
  unknown-source metadata and all original outputs remain unchanged.
- The three-condition primary pilot is **incomplete**: independent self-written
  reading audio has not been supplied. Personalized AI answers are not human
  negatives, and a reading delivery label alone does not establish AI use.
- Two same-settings ASR passes generated identical transcript-text hashes for all
  four inputs; audio transcript hashes exactly reproduce the previous ASR results.
  Both recordings passed existing quality guards, detected English, 113/140 words.
  No ASR editing, spelling correction, answer rewriting or text truncation.
- First preparation completed and verified files, but its process exited **134**
  during native teardown (`recursive_mutex lock failed: Invalid argument`). A new
  preparation directory was used for the retry; the retry exited **0** and retained
  the exact same transcript hashes. Root cause is not established; no forced exit
  or error-hiding workaround was used, and the earlier run remains preserved.
- Fast-DetectGPT scoring completed on both preparations with **clean exit 0**;
  all four raw statistics repeat exactly, zero loading/inference errors. All inputs,
  labels, source hashes and transcript hashes revalidated after scoring.
- Known AI pure-text control statistics were higher than the spontaneous recording's
  statistic in this diagnostic, but they are not spoken-AI positives and do not
  validate the end-to-end task. With user-confirmed provenance, the spoken-AI
  recording ranks above independent speech in this single pair. This does not
  establish correct classifications, a threshold, or accuracy.

## Software verification

- Added 27 synthetic mechanics tests: provenance/label preservation, text/audio
  cohort separation, unknown/personalized exclusions, frozen-source integrity,
  signed/nonfinite statistics, language/quality/length guards, no truncation,
  inference errors and lazy optional imports.
- Full native suite: **418 passed**, 0 failures/errors/skips, **23.59 s**, clean
  process exit. JUnit: `reports/pr5_validation/native-tests-verbatim-pilot-20261008.xml`.
- Source and cached model weights unchanged. Optional CLI added; core dependencies
  and backend/scoring API unchanged. Docker not rebuilt (previous 205-test image).
- No commit, push, PR or external interview-content upload.

## Remaining inputs

1. Supply independent self-written-and-read audio (and the original human script
   privately) if not already available. Do not use an assistant-generated script.
2. Retain exact original AI text privately if comparing pre-ASR and post-ASR
   behavior; the two synthetic controls are **different answers**, not that reference.

Private outputs: `data/processed/verbatim_pilot/cuda-graph-20261008/`.
Original detailed private report: `fast2/report.md` (initial provenance).
Latest private annotation: `provenance-confirmation-20261008.json`; it references
verified original hashes and reuses scores without rerunning ASR/inference.
Neither detailed artifact should be committed. No model/code changes were needed
for this confirmation. Protocol: [verbatim-pilot.md](../../docs/verbatim-pilot.md).
