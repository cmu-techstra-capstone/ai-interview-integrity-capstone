# ALLSSTAR VAD and Prosody Results

The paired audio experiment completed locally on 7 October 2026. Adding selected
prosody descriptors improved reading-versus-spontaneous classification on the
existing ALLSSTAR folds. Silero VAD plus prosody and RBF SVM reduced the
spontaneous-to-reading false-positive rate from 27.9% to 12.3%, with balanced
accuracy increasing from 73.9% to 83.4%. This is an exploratory result on a
previously evaluated cohort, not an independent test or an AI-use detector.

## Controlled comparison

All eight arms use the same 862 nonoverlapping 30-second windows, 408 source
recordings and 140 speakers as the [original experiment](first-run-20261007.md).
Class counts remain 148 reading and 714 spontaneous. No source, noise exclusion,
window length, transcript or demographic input was added. The original WAV
checksums matched, all original energy features reproduced exactly, and there
were zero extraction failures. The original model's metrics reproduced exactly.

Four feature groups were fixed before evaluation: energy-based timing/loudness
(14 features), the same features computed with Silero (14), and each of these
plus 20 selected eGeMAPS prosody descriptors (34 features). Prosody covers relative
F0 variability, pitch slopes, loudness variability, jitter, shimmer,
harmonic-to-noise ratio and voiced/unvoiced segment summaries. Absolute F0,
microphone level and task codes are not predictors, although indirect speaker,
language, noise and task effects remain possible.

Each group uses class-balanced Logistic Regression or RBF SVM, with fixed C=1
and no tuning. SVM uses gamma=scale. Median imputation and standardization fit
inside training folds. Five-fold StratifiedGroupKFold uses seed 42 and speaker
IDs; every row's fold assignment is identical across all arms, with zero
speaker overlap. There is no threshold adjustment, new test set, or ASR.

## Out of fold metrics

FPR means spontaneous windows predicted reading. Recall refers to reading.
The majority-class baseline has 50% balanced accuracy. Lower FPR alone is not
sufficient; recall must also remain useful.

| Features | Classifier | Balanced accuracy | Reading F1 | ROC AUC | FPR | Reading recall |
|---|---|---:|---:|---:|---:|---:|
| Energy 14, original | Logistic Regression | 73.90% | 0.4880 | 0.8122 | 27.87% | 75.68% |
| Energy 14 | RBF SVM | 75.14% | 0.5033 | 0.8405 | 26.75% | 77.03% |
| Silero 14 | Logistic Regression | 79.92% | 0.5598 | 0.8662 | 23.95% | 83.78% |
| Silero 14 | RBF SVM | 78.86% | 0.5548 | 0.8748 | 22.69% | 80.41% |
| Energy and prosody 34 | Logistic Regression | 83.74% | 0.6300 | 0.8852 | 17.65% | 85.14% |
| Energy and prosody 34 | RBF SVM | 82.17% | 0.6324 | 0.8990 | 14.71% | 79.05% |
| Silero and prosody 34 | Logistic Regression | 83.22% | 0.6308 | 0.8911 | 16.67% | 83.11% |
| Silero and prosody 34 | RBF SVM | 83.36% | 0.6629 | 0.9067 | 12.32% | 79.05% |

The Silero/prosody SVM is the candidate for further low-false-positive research,
not an approved replacement for the original baseline or production pipeline.
It has the lowest FPR and highest reading F1/ROC AUC among these eight arms.
Energy/prosody Logistic Regression instead has the highest balanced accuracy and
reading recall. Selecting between them requires a use-specific error tradeoff
and independent evaluation, not reporting only a preferred metric.

For the Silero/prosody SVM, reading precision is 57.07%, versus 36.01% originally.
The confusion matrix is:

| Actual class | Predicted spontaneous | Predicted reading |
|---|---:|---:|
| Spontaneous | 626 | 88 |
| Reading | 31 | 117 |

Spontaneous errors decrease from 199 to 88; reading misses decrease from 36 to
31. Task-specific errors remain: NWS 31/148 reading misses, ST1 29/331 false
positives, ST2 59/383 false positives. These differences support testing task
transfer rather than assuming general interview performance.

## VAD inspection

Across the paired windows, energy and Silero speech masks disagree for a mean
3.01 seconds per 30-second window (median 2.27, 90th percentile 5.89, maximum
26.74). This is detector disagreement, not a measured VAD error rate. Silero
detected no speech in seven windows; they remain in every comparison arm and
need manual review. Their undefined timing/loudness summaries are imputed only
inside training folds. All 20 selected prosody descriptors are finite in this run.

Twenty private listening examples are available under
`data/processed/allsstar/prosody-vad-20261007/audit/index.html`, with WAV clips,
both speech timelines and blank `human-review.csv` annotations. They are ten
strongest original-model false positives, five strongest false negatives and
five correct controls. No human listening review or reference speech-boundary
annotation has been completed. Neither model improvement nor agreement with
another detector establishes boundary accuracy.

## Artifacts and verification

Processing instructions and settings:
[Audio VAD and Prosody Experiment](../../docs/audio-delivery-experiment.md).
Feature/diagnostic outputs and listening samples total 22,340,599 bytes. The eight
model directories and their local per-window reports total 1,961,097 bytes. All
are Git-ignored; original model and data outputs remain unchanged. Only this
aggregate report and code/documentation are suitable for repository inclusion.

Native tests: 240 passed, zero failures/errors/skips. CLI help, source checksum
guards, original-feature reproduction, identical folds and trusted model reloads
were verified. Test report:
`reports/pr5_validation/native-tests-audio-prosody-20261007.xml`. Docker has not
been rebuilt for these optional dependencies and remains at its earlier
205-test image.

Environment: macOS arm64, Python 3.13.7, NumPy 2.5.3, scikit-learn 1.9.1,
openSMILE 2.6.0, silero-vad 6.2.3, PyTorch 2.14.1 and ONNX Runtime 1.30.0.
The bundled Silero ONNX SHA-256 is
`1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`.
The adapter disables ONNX telemetry. No audio was uploaded, no ASR was run,
and no commit, push or PR was created.

## Remaining validation

Complete the listening audit, especially no-speech detections and high-disagreement
windows. Then test unseen tasks and consented technical-interview recordings with
disjoint speakers, reporting participant-level uncertainty and language slices.
The eight-arm comparison uses previously examined folds and cannot independently
confirm the chosen candidate's performance. Windows from one speaker are
correlated, and no confidence intervals or calibrated probabilities are claimed.

Reading a passage versus describing a picture differs in task demands, not just
delivery. Fluency, accents, noise and speech differences can affect features.
Reading is neither necessary nor sufficient for AI use; no automatic cheating
verdict or hiring decision is supported.

The feature extractors are [Silero VAD](https://github.com/snakers4/silero-vad)
and [openSMILE eGeMAPSv02](https://audeering.github.io/opensmile-python/usage.html).
[openSMILE's licence](https://audeering.github.io/opensmile-python/#license)
distinguishes research from commercial-product use; commercial integration
requires a separate licensing decision.
