# Audio / Transcript Research Update — 2026-10-08

## Current MVP

Assess substantially verbatim AI-generated answers, using candidate-only audio
through local ASR and an offline text detector. Human editing and paraphrasing
are outside this MVP's headline evaluation; they are not reclassified as
independent human answers. The client's broader prohibition on AI assistance
is unchanged. Existing exploratory robustness reports remain as historical
research records, not primary MVP results.

Current experimental route: audio -> faster-whisper small CPU/int8 -> unchanged
transcript -> Fast-DetectGPT, GPT-Neo 2.7B as both reference and scorer.
This is a research CLI, not integrated into production scoring. No new detector
training or fine-tuning has been performed; no probability calibration, operating
threshold, hiring verdict, or model fusion is implemented.

## Public written-text evaluation

Beemo selection: 200 frozen prompt groups, 600 texts. Fair comparisons below
use the identical 90 complete groups retained across all evaluated variants
and methods (45% group coverage); each displayed binary comparison contains
90 human-original and 90 original-AI texts. No excluded examples were replaced.
English, at least 50 words, at most 512 tokens; no truncation or rewriting.

| Method | Original AI vs human AUROC | 95% paired-prompt bootstrap interval |
| --- | ---: | --- |
| MAGE, publisher cleanup, AI-class logit | 0.7581 | 0.6890–0.8190 |
| SuperAnnotate, publisher cleanup | 0.6985 | 0.6233–0.7735 |
| Fast-DetectGPT, GPT-Neo 2.7B | **0.8535** | **0.7952–0.9030** |

AUROC is ranking separation, **not 85.35% accuracy**. This previously inspected
written benchmark is not blind interview/ASR validation. Training overlap with
upstream checkpoints has not been audited. The smaller supported GPT-Neo
configuration is not the recommended larger Llama3 model pair.
Detailed protocol, coverage and historical experiments:
[benchmark](../reports/beemo/paired-text-20261008.md),
[follow-up](../reports/beemo/detector-followup-20261008.md).

## Local spoken proof of concept

Two consented existing personal recordings of one familiar technical topic were
processed using identical ASR settings. The user subsequently confirmed one
independent answer and one reading of an assistant-generated standard answer:
self-reported provenance, not independently protocol-verified or blind testing.
The spoken AI sample ranks above the independent sample under the raw discrepancy
statistic. ASR text hashes and all detector scores repeated exactly across two
runs. This demonstrates an operational pipeline and expected ordering in one
pair, not correct binary classifications or an interview accuracy estimate.

Personal recordings, scripts, transcripts, provenance annotations and detailed
individual scores remain local and ignored. Aggregate execution status:
[pilot status](../reports/verbatim/pilot-status-20261008.md).

## Earlier audio research and infrastructure

- ALLSSTAR reading/spontaneous experiments use 862 windows and 140 speakers with
  speaker-separated folds. The Silero/prosody SVM exploratory arm achieves
  balanced accuracy 0.834 and AUROC 0.907. **This is a delivery classifier, not
  an AI-use classifier**, and is not the current MVP's AI-detection metric.
- PR #5 validation: Docker and its then-current 205-test suite completed;
  small Docker packaging and STT failure-reporting/alignment-cache fixes included.
- Four ASR configurations completed the same 20 Michigan clips. Unprompted
  faster-whisper small WER 0.1534; this courtroom subset does not establish
  interview-domain ASR performance. Full research dependencies are optional.
- Full native research suite rerun before PR publication: **418 passed in 20.43 s**,
  clean process exit; [JUnit](../reports/pr5_validation/native-tests-pr-sync-20261008.xml).
  Software tests verify mechanics, not detection quality. Native teardown failures
  encountered in earlier runs are documented; no forced-success workaround.

## Teammate quick start

This branch is stacked on PR #5's `feature/docker-stt-staged-readiness`, not on
`main`. Review only the delta above PR #5; do not merge or alter PR #5 as part of
this research PR. Use a separate checkout if keeping your current branch intact.

```sh
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev,ml]'
.venv/bin/python -m pytest -q
.venv/bin/verbatim-pilot --help
```

Core code remains standard-library-only. Optional deep-model parity tests require
the additional research extras; a minimal install does not reproduce every test
from the fully provisioned 418-test environment. No dataset or weight download is
required for the basic test suite; heavier research dependencies and explicit
download/reproduction commands are described in:
[verbatim pilot](verbatim-pilot.md), [detector follow-up](detector-followup.md),
[ALLSSTAR](allsstar-audio.md), [audio delivery experiment](audio-delivery-experiment.md).

Do not commit raw datasets, weights, audio, transcripts or detailed personal
outputs. Regenerated Michigan feature files in the developer's local checkout
are deliberately excluded from this PR. No production scoring/API changes.

## Next validation

1. Collect independently human-written-and-read audio as a negative control for
   reading delivery; do not use an assistant-written script for that condition.
2. Collect consented multi-speaker, multi-topic independent and AI-verbatim answers;
   preserve source labels and keep speakers/questions separate in evaluation.
3. Specify any calibration/threshold protocol before using new held-out test data;
   only then report sensitivity, false-positive rate, precision or accuracy.

Suggested update to teammates: “The optional audio-to-ASR/text research pipeline
is implemented and tested. Fast-DetectGPT achieved 0.8535 AUROC on the retained
original-AI Beemo comparison. One real spoken pair shows expected ordering, but
we still need self-written reading controls and independent interview validation.”
