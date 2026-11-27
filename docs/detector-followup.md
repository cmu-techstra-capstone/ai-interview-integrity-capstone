# Fixed-input detector follow-up

Standalone local research, not a production model, scoring API or hiring decision.
The original Beemo run and manifest remain untouched. This is a follow-up on a
previously inspected dataset, **not a new blind independent validation**.

## What is compared

1. Original HC3, MAGE and SuperAnnotate results from the frozen 200 prompt groups.
2. MAGE after its publisher preprocessing, with both class-0 logit and softmax
   rankings. The publisher uses a class-0 logit cutoff, not softmax > 0.5. We do not
   tune or adopt a cutoff for interviews. A cutoff change does not improve AUROC.
3. SuperAnnotate after its publisher preprocessing, with its unchanged custom
   single-logit GENERATED sigmoid head.
4. Fast-DetectGPT analytic conditional sampling discrepancy using the same pinned
   GPT-Neo 2.7B model as reference and scorer. This is an author-supported smaller
   baseline, **not the stronger recommended Llama3-8B / Llama3-8B-Instruct pair**.

HC3 has no added cleanup arm. We are checking known publisher pipeline differences,
not inventing normalization rules or LLM-rewriting transcripts.

## Provenance and runtime differences

Publisher preprocessing bytes are downloaded explicitly to ignored
`.cache/publisher-cleanup/`, checksum-verified and restricted to reviewed AST
definitions; no publisher web service, detector/training code, or model download
code is executed. This is not a general code sandbox: source review + checksum
pins are the trust boundary. Definitions reproduce the exact reviewed cleaning
functions. We retain the current pinned local checkpoint adapters and current
Transformers runtime, **not the publishers' entire older deployment environments**.

- [MAGE source](https://github.com/yafuly/MAGE/blob/6d11f851184b9f04166f952ddc1f47727f36710f/deployment/utils.py):
  SHA-256 `64791a5c776ad56e2896ffd51c351c806db3cb35bd66194b3b933eba19625cec`.
  Moses punctuation normalization, tokenization normalization, clean-text,
  URL/email/phone removal, ASCII conversion and whitespace normalization.
- [SuperAnnotate source](https://github.com/superannotateai/generated_text_detector/blob/dbd6317968d144291192a2baf33e11df4e6cdf65/generated_text_detector/utils/preprocessing.py):
  SHA-256 `7631916d1fc2434a2b5471363310ee3d4b371c249f44177470d71463ce49a9a3`.
  Zero-width removal, publisher homoglyph mapping, Markdown -> HTML -> BeautifulSoup
  text, URL/email removal and whitespace normalization. No corrected/expanded map.
- Small cleanup dependencies are pinned in the optional `text-cleanup` extra.
  Actual runtime versions are recorded. Core and Docker dependencies unchanged.
- [Fast-DetectGPT method](https://github.com/baoguangsheng/fast-detect-gpt/blob/971b05202bac2bb504d60c0ac0812fea7a8f7c82/scripts/fast_detect_gpt.py)
  is MIT; model weights are [EleutherAI/gpt-neo-2.7B](https://huggingface.co/EleutherAI/gpt-neo-2.7B),
  MIT, revision `e24fa291132763e59f4a5422741b424fb5d59056`.
  Download only `model.safetensors` (10,672,390,984 bytes) plus small tokenizer/config
  files; not duplicate bin/Flax/Rust weights. Local float16, no quantization or remote
  code. Explicit CPU/MPS only; no silently chosen cloud/GPU/device fallback.
  Loading rejects missing active parameters, mismatched tensor shapes and unknown
  keys; only legacy causal-attention `bias`/`masked_bias` buffers may be ignored.
  The output head must be the checkpoint head or explicitly tied input embeddings,
  never an independently initialized random head.
- The raw criterion is `(observed log-likelihood - reference expected
  log-likelihood) / sqrt(sum of reference variances)`. All token IDs/vocabulary must
  align. Same model gives identical reference/scorer distributions. Formula uses
  float64 CPU reductions and centered variance for numerical stability; a synthetic
  parity test checks algebraic equivalence with the original formula. Different
  hardware/precision means bitwise publisher parity is not claimed.
- Do not use the demo's distribution-to-probability mapping as interview confidence.
  We report the raw signed statistic only: higher means more machine-like under
  the method, not a calibrated probability of external assistance.
- Existing MAGE/SuperAnnotate weight terms and Beemo upstream restrictions still
  apply. Research access is not blanket approval for hiring-system deployment.

## Fixed evaluation protocol

- Reuse the exact original 200-group, three-variant manifest and hashes; no new
  sampling, replacements, prompts/labels in model input, training or threshold fit.
- Minimum 50 words before preprocessing; additionally reject text falling below
  50 words after cleanup. Maximum 512 tokens including special tokens; no truncation.
  This common capacity is a comparison control, not a claim of maximum GPT-Neo context.
- Store raw and processed text hashes, counts, statuses, signed statistics and
  timings. Do not publish source text or personal transcripts.
- Primary comparisons use the intersection of the **original 90 complete groups**
  and all arms in a run; reuse the same matched groups for every row and contrast.
  Report dropped original groups and full 200-group coverage. Across separate
  follow-up runs, only compare headline metrics if their matched IDs are identical;
  otherwise recompute all arms on their joint intersection first.
- Report AUROC and 1,000 paired-prompt bootstrap percentile intervals. Overlapping
  intervals do not prove a difference or equivalence. AUROC is not accuracy.
- Errors persist as errors/null scores and make the command fail, rather than
  silently becoming human predictions or successful validation. Changed inputs
  invalidate the run; existing output directories cannot be overwritten.

## Reproduce

Run from the repository root, after installing optional `text-research`,
`text-benchmark` and `text-cleanup` dependencies. Downloads are the only network steps.

```sh
.venv/bin/python -m interview_integrity.modeling.detector_followup download-cleanup
.venv/bin/python -m interview_integrity.modeling.detector_followup download-fast
```

Offline publisher comparison:

```sh
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
.venv/bin/python -m interview_integrity.modeling.detector_followup publisher \
  --manifest data/processed/beemo/20261008/protocol/manifest.json \
  --baseline data/processed/beemo/20261008/run1/results.json \
  --out-dir data/processed/beemo/20261008/publisher-new
```

Offline smaller Fast-DetectGPT comparison (MPS must actually be available):

```sh
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=.cache/huggingface \
.venv/bin/python -m interview_integrity.modeling.detector_followup fast --device mps \
  --manifest data/processed/beemo/20261008/protocol/manifest.json \
  --baseline data/processed/beemo/20261008/run1/results.json \
  --out-dir data/processed/beemo/20261008/fast-new
```

All results and weight caches remain ignored. No ASR is rerun, interview content
uploaded, fusion added, or production threshold selected. Audio timing and
interview-domain adaptation require a separate labeled pilot and are not part of
this experiment. See the [aggregate follow-up report](../reports/beemo/detector-followup-20261008.md)
for completed publisher comparisons and the explicitly recorded Fast-DetectGPT status.
