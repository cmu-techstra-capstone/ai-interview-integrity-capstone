# HANSEN-TT test-only evaluation: Desklib detector

## Setup

- Dataset: HANSEN Turing Test (TT) archive; official `test.csv` files only.
- Labels: `0 = human`, `1 = AI-generated`.
- Detector: `desklib/ai-text-detector-v1.01`, pinned revision `5fdea974cd4287c61674951ec78803aa274e2fb7`.
- Model use: pretrained inference only; no fine-tuning, threshold selection, or calibration.
- Rows in test split: 11,594 across 15 generator/domain groups.

## Results

- **Overall AUROC: 0.9941** on the scored subset.
- Scored: 3,472/11,594 (**29.9% coverage**); 8,122 texts were longer than the model's 512-token limit and were excluded, not truncated.
- Mean AI-text score among scored rows: human **0.1092**, AI **0.9760**. These are model scores, not calibrated probabilities.

| Generator | Rows | Scored | AUROC |
| --- | ---: | ---: | ---: |
| ChatGPT | 3,929 | 1,151 | 0.9884 |
| PaLM | 3,555 | 917 | 0.9964 |
| Vicuna-13B | 4,110 | 1,404 | 0.9965 |

| Domain | Rows | Scored | AUROC |
| --- | ---: | ---: | ---: |
| CEO | 74 | 29 | 1.0000 |
| SEC | 359 | 95 | 1.0000 |
| Spotify | 4,237 | 1,308 | N/A* |
| TED | 4,244 | 527 | 0.9989 |
| Tennis | 2,680 | 1,513 | 0.9998 |

*AUROC is not estimable when only one label class remains after the 512-token exclusion. Some generator/domain subgroups therefore also have N/A results; see the ignored local aggregate report for the full table.

## Interpretation and limits

This is a strong ranking result on the **short-text subset** of a held-out, spoken-style text benchmark. The 29.9% coverage and missing-class subgroups mean the headline is conditional on length and is not representative of all HANSEN rows. HANSEN contains human and generated text, not interview audio, ASR transcripts, technical interview answers, or verified real-time AI assistance. Therefore, this does **not** establish that a candidate used AI, nor does it validate a hiring or interview-integrity decision.

No raw text or per-row scores are included in this report. The source archive and detailed output remain git-ignored. The local aggregate JSON records the archive SHA-256 and the full per-group metrics.

Sources: [HANSEN dataset card](https://huggingface.co/datasets/HANSEN-REPO/HANSEN), [Desklib detector model](https://huggingface.co/desklib/ai-text-detector-v1.01).

## Reproduce

Obtain the HANSEN-TT archive through the authors' request process, install the
local text-research dependencies and model weights, then run from the repository
root. The output directory must be new and remains under ignored
`data/processed/`:

```bash
python -m pip install -e ".[text-research]"
python -m interview_integrity.modeling.hansen_benchmark \
  --archive data/raw/hansen_tt/HANSEN-TT.zip \
  --out-dir data/processed/hansen_desklib_report
```

The evaluator runs the pinned pretrained detector on test rows only; it does not
fine-tune the model and saves aggregate results only.
