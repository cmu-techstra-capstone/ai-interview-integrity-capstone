# Beemo external paired-text stress test — 2026-10-08

This is an aggregate report without source text or personal interview content.
It evaluates the current raw-text checkpoint adapters, NOT live interview
AI-assistance detection or the audio -> ASR -> detector pipeline.

## Frozen inputs and protocol

- Public dataset: [toloka/beemo](https://huggingface.co/datasets/toloka/beemo),
  revision `9c014107fe9b85c4c784c1ce3a43b0b7b0a6d162`.
- Download: 8,345,056-byte parquet, 2,187 distinct prompt groups.
- Source SHA-256: `5df88f7941e873db3c6e2be4e4085db50fa824f7fc626685f0e317e935a188db`.
- Selection frozen before scoring: seed `20261008`, 200 prompt groups,
  40 each from Closed QA, Generation, Open QA, Rewrite and Summarize.
- Ten source generators represented. No sampling based on scores or length.
- Three texts per group: `human_output` (negative), `model_output` (positive),
  `human_edits` (hybrid AI-assisted positive). Human editing does not erase AI
  assistance under this project's definition. LLM-editor fields are NOT tested.
- Three unchanged pinned adapters: HC3, MAGE, SuperAnnotate. English only;
  at least 50 words and at most 512 tokens including special tokens; no truncation,
  rewriting, ASR, fine-tuning, threshold selection, model winner or fusion.
- Boundary whitespace stripped consistently. Publisher-specific cleanup is not
  reproduced; results do not claim to reproduce published deployment metrics.
- All 1,800 sample/model rows completed. 1,191 scored, 609 abstained by guards;
  **0 model-loading or inference errors**. Source/manifest hashes verified unchanged.

## Comparable results

All THREE variants and all THREE models scored a common set of **90 / 200 groups
(45%)**. The following metrics use that exact common set for every comparison.
No excluded examples were replaced. Metrics are therefore conditional on retained
texts, not an estimate for all 200 groups or interview candidates.

AUROC measures ranking separation: 0.5 is chance and 1.0 is perfect. It is NOT
accuracy, sensitivity, specificity, or a calibrated probability. Intervals are
percentile 95% CIs from 1,000 resamples of paired prompt groups using the fixed seed.

| Model | Original AI vs human AUROC | 95% CI | Expert-edited AI vs human AUROC | 95% CI |
| --- | --- | --- | --- | --- |
| HC3 | 0.7019 | [0.6369, 0.7648] | 0.5067 | [0.4373, 0.5803] |
| MAGE | 0.7451 | [0.6827, 0.8049] | 0.6184 | [0.5516, 0.6826] |
| SuperAnnotate | 0.6928 | [0.6195, 0.7689] | 0.6232 | [0.5587, 0.6874] |

All six AUROCs were independently checked with scikit-learn `roc_auc_score`;
agreement within 1e-12. These are software/metric checks, not independent replications
on another dataset. Bootstrap uncertainty excludes domain shift, dataset exclusions,
unknown training overlap and annotator/author dependence.

| Model | Human mean AI score | Original AI mean score | Expert-edited AI mean score | Edited minus original mean |
| --- | --- | --- | --- | --- |
| HC3 | 0.5063 | 0.8063 | 0.5482 | -0.2581 |
| MAGE | 0.8341 | 0.9768 | 0.8876 | -0.0892 |
| SuperAnnotate | 0.6102 | 0.7191 | 0.6755 | -0.0436 |

Scores are uncalibrated and not interchangeable across models. High scores on
AI text alone do not establish useful separation: human text can score high too.
No binary false-positive rate or accuracy is estimated without a separately
specified and evaluated operating threshold. MAGE's publisher raw-logit cutoff
is not applied; these are softmax scores in the declared raw-text adapter protocol.

## Coverage and selection effects

All three adapters have the same coverage here. Counts below are per model.

| Variant | Selected | Scored | Under 50 words | Over 512 tokens | Unscored |
| --- | --- | --- | --- | --- | --- |
| Human | 200 | 110 | 84 | 6 | 45.0% |
| Original AI | 200 | 151 | 35 | 14 | 24.5% |
| Expert-edited AI | 200 | 136 | 57 | 7 | 32.0% |

The original equal category quotas do NOT survive the complete-group filter:

| Category | Initially selected | Common complete groups |
| --- | --- | --- |
| Closed QA | 40 | 2 |
| Generation | 40 | 24 |
| Open QA | 40 | 23 |
| Rewrite | 40 | 26 |
| Summarize | 40 | 15 |
| Total | 200 | 90 |

The current guards exclude many short answers, particularly Closed QA. Report
coverage alongside AUROC; this benchmark does not validate short interview answers.
Changing guards/chunking later would be a new predefined experiment, not a silent
replacement of this result.

## Interpretation

- Ranking separation on retained original AI texts is moderate (AUROC ~0.69-0.75),
  not evidence of the often-advertised near-perfect detection accuracy.
- Expert-edited versions have lower AUROC for every checkpoint. HC3 is near chance
  on that contrast; MAGE/SuperAnnotate retain limited separation (~0.62).
- Expert editing is written revision, not spoken personalization. These findings
  flag a robustness issue but do not quantify performance on AI-personalized interviews.
- Confidence intervals overlap across candidates; no winner or statistical superiority
  is established. Do not choose an operating threshold using these results.
- Pretrained training data are not fully auditable. This is an external dataset test,
  not a guaranteed clean unseen test set. Component licences also differ; review
  [upstream terms](https://github.com/Toloka/beemo#license) before deployment or redistribution.
- Next evidence needed: verified human-only and AI-assisted spoken answers under
  identical ASR conditions, preserving fluent human controls and AI-personalized cases.

## Reproduction and software verification

See [workflow/protocol](../../docs/beemo-benchmark.md). Private protocol and detailed
outputs remain in ignored `data/processed/beemo/20261008/`; the parquet is cached
under ignored `.cache/datasets/beemo`. Do not commit raw text or individual outputs.

35 new offline benchmark mechanics tests cover seeded sampling, paired labels,
input integrity, score isolation, AUROC/ties, bootstrap, abstention and failure paths.
Full native suite: **369 passed**, 0 failures/errors/skips, clean exit in **16.42 s**.
The optional strict encoder/head test now runs in a checked subprocess to separate
heavy text runtimes from optional audio libraries. An earlier full run passed all
assertions but aborted during native-library teardown (exit 134); its root cause
is not established and its JUnit report is preserved. No forced successful exit
or skipped parity assertions conceal the failure. Docker remains at 205 tests.

Clean report: `reports/pr5_validation/native-tests-beemo-20261008-isolated.xml`.
Model inference itself also exited cleanly. No personal recording/transcript upload,
production change, commit, push or PR was made for this experiment.
