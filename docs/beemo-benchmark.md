# Beemo paired-text benchmark

Optional external written-text stress test, implemented 2026-10-08. It evaluates
the current HC3/MAGE/SuperAnnotate checkpoint adapters, not live interview
assistance, the audio-delivery classifier, or ASR. No production services changed.

## Public source and permissions

- Dataset: [toloka/beemo](https://huggingface.co/datasets/toloka/beemo).
- Pinned revision: `9c014107fe9b85c4c784c1ce3a43b0b7b0a6d162`.
- File: `data/train-00000-of-00001.parquet`, 8,345,056 bytes; 2,187 rows.
- Original parquet SHA-256: `5df88f7941e873db3c6e2be4e4085db50fa824f7fc626685f0e317e935a188db`.
- No access request is needed for this public file. Only public data is downloaded;
  no personal interview audio, transcripts or outputs are uploaded.
- Upstream terms differ by component: human text/prompts inherit No Robots
  CC-BY-NC-4.0; generated versions inherit model terms; expert edits have MIT
  terms subject to underlying-model restrictions. The overall MIT card tag is
  not a blanket commercial permission. See the
  [authors' component licence statement](https://github.com/Toloka/beemo#license).

The inspected pinned source has 2,187 distinct `prompt_id` values. It covers five
task categories and ten generators. It is NOT technical interview speech, and
expert editing is NOT the same as natural spoken personalization. Training-data
overlap cannot be fully audited for the pretrained checkpoints: describe this as
an external benchmark, not guaranteed unseen independent data.

## Frozen protocol

Before any scoring, select 200 prompt groups: 40 each from Closed QA, Generation,
Open QA, Rewrite and Summarize. Within each category, order prompt IDs by a
SHA-256 hash incorporating seed `20261008`, and take the first quota. Sampling
does not depend on model scores, lengths, model preference or content inspection.
If a prompt had multiple source rows, choose one deterministically before scoring;
do not repeat the same human answer as multiple independent examples.

Each selected row provides the following complete candidate-output texts. Prompts,
source names and labels are metadata only; none are passed into a detector.

| Variant | Source field | Project binary label | Meaning |
| --- | --- | --- | --- |
| human | `human_output` | 0 | Dataset human-authored answer |
| ai_original | `model_output` | 1 | Original machine-generated answer |
| ai_expert_edited | `human_edits` | 1 | AI-origin answer revised by a human expert; hybrid AI-assisted positive |

The two additional LLM-editor fields are not evaluated in this first run. No
general claim about all Beemo variants, colloquial speech or AI-personalized
interviews follows from this three-variant result.

Store all 600 texts and provenance in an ignored manifest before loading models.
Only surrounding whitespace is stripped, matching the current Transcript.text
interface. Do not rewrite, correct, regenerate or truncate text. Use the already
cached, pinned CPU model adapters and their verified AI-score direction:
HC3 class 1, MAGE class 0, SuperAnnotate single-logit sigmoid. Do not use arbitrary
Hub code or change weights. Publisher-specific cleaning is not applied here;
this is not an exact reproduction of authors' deployment benchmarks.

Retain the existing 50-word minimum and 512-token common maximum, including special
tokens. These engineering guards are not scientific reliability thresholds.
Flagged examples stay in the manifest and coverage denominator: do not replace
them with convenient longer/shorter examples. Loader/inference failures have null
scores, not zero. No ASR is run: these are public written outputs.

## Metrics

- Report scored counts, abstention reasons and unscored fractions separately for
  each model and variant on the full 200-group selection.
- For comparisons, take the intersection of groups for which all THREE variants
  received valid scores from all THREE models. Use exactly that same common set
  for both contrasts and every model; do not compare differently filtered groups.
- Compute threshold-free, tie-aware AUROC for original AI vs human, and edited AI
  vs human. 0.5 indicates chance ranking and 1.0 perfect ranking; **AUROC is not
  classification accuracy, sensitivity or a cheating probability**.
- Report percentile 95% bootstrap intervals using 1,000 paired-prompt resamples
  and the fixed seed. These describe sampling variability on retained groups,
  not uncertainty from training overlap, domain transfer or exclusions.
- Also retain paired score means and change after expert editing. Different
  checkpoints are not calibrated against each other; absolute scores are not
  interchangeable probabilities.
- No threshold fitting, binary accuracy estimate, model selection, fine-tuning,
  multimodal score fusion or hiring judgement.

## Reproduce

Run from the repository root. The source, model weights and per-example outputs
remain under ignored directories. Core/Docker dependencies are unchanged.

```bash
.venv/bin/python -m pip install -e '.[text-research,text-benchmark]'

HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
  .venv/bin/python -m interview_integrity.modeling.beemo_benchmark download

HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
  .venv/bin/beemo-benchmark prepare --groups 200 --seed 20261008 \
  --out-dir data/processed/beemo/reproduction/protocol

HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
  .venv/bin/beemo-benchmark run \
  --manifest data/processed/beemo/reproduction/protocol/manifest.json \
  --out-dir data/processed/beemo/reproduction/run1
```

Provision model weights separately with `transcript-compare download` if absent.
Both preparation and inference use local cache only; only the explicit download
command accesses the network. Choose new output directories; existing results
are never overwritten. The CLI requires output under ignored `data/processed`.

For this run, the frozen manifest is
`data/processed/beemo/20261008/protocol/manifest.json`; detailed outputs are in
`data/processed/beemo/20261008/run1/`. Every 50 processed examples, `results.json`
is checkpointed with `integrity_status=pending` and `run_status=running`.
Summaries are created only after the original dataset and manifest hashes are
verified again. Interrupted/changed-input runs are not valid benchmark evidence.
Progress output contains counts, not sample text.

Do not commit raw parquet, selected text, provenance manifests or per-example
outputs. A lightweight aggregate report can be shared without redistributing
source text or personal interview information. Use actual consented interview
recordings with verified assistance conditions for subsequent domain validation.

## Completed run

See [aggregate results](../reports/beemo/paired-text-20261008.md): 200 frozen groups,
1,800 sample/model rows, 0 inference errors, 90 common complete groups. Original-AI
AUROC ranges 0.6928-0.7451; expert-edited AUROC ranges 0.5067-0.6232. This is not
classification accuracy. All six values were independently verified with
scikit-learn. Important selection effect: just 2 of 40 Closed QA groups remain
in the common set. No model/threshold selected, no new training or ASR run.

35 new benchmark mechanics tests passed. Full native suite: 369 passed, no
failures/errors/skips, clean exit in 16.42 s after isolating the optional heavy
encoder/head parity test in a checked child process. Earlier native teardown
abort is recorded, not treated as a successful process run. Docker not rebuilt.
