# HANSEN-TT: self-trained text baseline and leakage audit — 2026-10-23

## Why this experiment

The project already had a pretrained Desklib result of AUROC 0.9941, but only
on 29.9% of test rows that fit its 512-token input limit. This experiment checks
whether the currently accessible HANSEN data can train a small project-owned
text model with full response coverage. It is an authorship benchmark, not a
test of real-time AI use during interviews.

## Leakage audit

Before interpreting a self-trained result, normalized exact-text hashes were
compared across HANSEN's official train and test splits. The audit found **4,691
unique texts shared across the splits**, accounting for **5,552 test-row
occurrences** and **7,235 training rows removed**; the shared texts had the same
human label in both splits. Human
examples are repeated across multiple generator/domain group files. A naive
train/test run therefore risks evaluating memorized source passages.

For the reported run, all training rows whose normalized text appeared anywhere
in test were removed; the remaining training data was de-duplicated. Test data
was also de-duplicated by normalized text. No transcript text or per-example
prediction was persisted.

## Experiment

- Training: 20,475 unique HANSEN training texts after decontamination.
- Test: 10,313 unique normalized texts from the official test split.
- Input: first 512 whitespace-delimited tokens per text.
- Model: word unigram/bigram TF-IDF, 50,000-feature cap, logistic regression
  (`C=1`, `liblinear`, fixed seed 0); no pretrained model or external detector.
- Result: **AUROC 0.9985**, with **100% test-row coverage** under this windowing.
- Leave-one-generator-out AUROC (train on the other two generators; exclude all
  exact text shared with any test sample): ChatGPT **0.9993**, PaLM **0.9907**,
  Vicuna-13B **0.9982**.

These are dataset-specific ranking results. The exceptionally high scores are
not evidence of comparable performance on candidates or interviews: the human
and AI classes in HANSEN differ by source and generation process, and the
benchmark contains older LLM outputs, not real-time assistance, ASR transcripts,
technical interview answers, or candidate-controlled paraphrases. A random
row split would be invalid; even a deduplicated split does not remove all
source/domain artifacts. Do not use this model or score for candidate decisions.

## Comparison and next dataset/model checks

Desklib's 0.9941 result and this 0.9985 result are **not a head-to-head
comparison**: Desklib abstained on long rows and its aggregate includes repeated
group rows, while this baseline used unique normalized text and a 512-word
window. No threshold, accuracy, calibrated probability, or model winner is
claimed. The runnable implementation is
`src/interview_integrity/modeling/hansen_tfidf_baseline.py`.

## Reproduce

Obtain the HANSEN-TT archive through the authors' request process, then run from
the repository root (install `.[ml]` first if scikit-learn is not installed):

```bash
python -m pip install -e ".[ml]"
python -m interview_integrity.modeling.hansen_tfidf_baseline \
  --archive data/raw/hansen_tt/HANSEN-TT.zip \
  --out data/processed/hansen_tfidf_summary.json
```

The command writes aggregate metrics only. The archive, transcript text, and
row-level predictions are not written or included in Git. For the fixed
pretrained Desklib comparison, see the companion
[evaluation report](hansen-tt-desklib-test-2026-10-22.md).

RAID is a useful broad robustness benchmark (multiple generators, domains,
decoding settings, and attacks), but it is huge: the project lists 802 MB for
the non-adversarial train split and 11.8 GB with adversarial data. It is general
machine-generated text, not interview-use ground truth. APT-Eval is a much
smaller (about 15K examples) AI-polishing benchmark and can help measure false
alarms on lightly AI-edited human writing; under the current project label
policy, it should be a boundary/negative-control set, not a positive training
set. Neither replaces staged interview pilots.

TMR (a RAID-trained RoBERTa detector) is a plausible public challenger, but its
model card's performance claims are on RAID. A local download attempt could not
reach the Hugging Face Hub due to a DNS/network failure, so no result is claimed
and no model was added. Revisit it when model downloads are available.

## Product direction decision

The project should not optimize “AI-written text” as a proxy for “candidate used
AI live.” The core target is an **unauthorized assistance event during an
interview**. Text authorship is only one weak evidence channel. The MVP should
combine interpretable, quality-checked signals with event/context evidence,
keep the output as a review cue, and validate on consenting staged interviews
with known no-assistance, AI-verbatim, and AI-personalized conditions. The MIT
audio archive is useful for audio/ASR mechanics but has no AI-assistance labels.

## Sources

- [HANSEN dataset card](https://huggingface.co/datasets/HANSEN-REPO/HANSEN)
- [Desklib model card](https://huggingface.co/desklib/ai-text-detector-v1.01)
- [RAID benchmark repository](https://github.com/liamdugan/raid)
- [TMR model card](https://huggingface.co/Oxidane/tmr-ai-text-detector)
- [APT-Eval dataset card](https://huggingface.co/datasets/smksaha/apt-eval)
