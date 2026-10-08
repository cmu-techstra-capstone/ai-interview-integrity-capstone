# Audio Delivery Baseline

The optional `audio-baseline` command implements a reading-versus-spontaneous
delivery experiment using existing pipeline audio features. It is not an
AI-assistance detector. The first real ALLSSTAR experiment completed on 2026-10-07:
862 windows, 140 speakers and five-fold speaker-separated evaluation; balanced
accuracy 0.739, reading F1 0.488 and ROC AUC 0.812. See the
[experiment report](../reports/allsstar/first-run-20261007.md) for false positives
and task-transfer limits. Synthetic unit tests verify software mechanics separately.

A paired follow-up using Silero VAD, 20 selected prosody descriptors and RBF SVM
achieved balanced accuracy 0.834 and FPR 12.3% on the same folds. It is exploratory,
not a new independent test or a default model change. See
[VAD and prosody results](../reports/allsstar/prosody-vad-20261007.md).

## Existing Michigan Data

Michigan is already usable for processing and ASR experiments: 121 clips, 61
`DECEPTIVE` and 60 `TRUTHFUL`, with reference transcripts and regenerated features.
The extracted audio totals approximately 56.4 minutes. Its delivery mode is not
labeled, every AI-assistance label is `UNKNOWN`, and participant IDs are unknown
placeholders. These labels must not be renamed to `READING`, `SPONTANEOUS`, or AI-use
conditions.

A Michigan truthful/deceptive classifier can be a separate pipeline exercise, but
would answer a different research question. Recording-grouped evaluation cannot
demonstrate unseen-speaker generalization without genuine speaker IDs. No such proxy
classifier has been fitted in this branch.

## Model and Features

The baseline uses median imputation, standardization, and class-balanced Logistic
Regression with fixed settings. All preprocessing is fitted only on each training
fold. Evaluation uses participant-grouped stratified cross-validation, not random
row splits. A most-frequent dummy baseline is evaluated on the same folds.

By default, 14 acoustic features describe speech/silence durations, pauses, speech
segment lengths, and loudness variation. It excludes transcripts, labels, participant
identifiers, source names, recording-quality flags and absolute microphone level.
`--include-transcript-rates` adds speech rate, articulation rate and speech-rate
variation, so that run is no longer transcript-independent.

Metrics include out-of-fold balanced accuracy, reading-class F1, ROC AUC and a
confusion matrix with class order `[SPONTANEOUS, READING]`. Final model weights use all
eligible labeled rows after evaluation; reported metrics come only from held-out
folds. Outputs are uncalibrated research predictions, not cheating probabilities.

## Required Input

Features can be the pipeline's combined CSV, a JSONL file, or a directory of flat
combined feature JSON files. Keep the ground-truth label CSV separate, with columns:

```text
recording_id,question_id,participant_id,delivery_label,label_source
```

`delivery_label` must be `READING` or `SPONTANEOUS`. `label_source` must be
`controlled_protocol` or `dataset_annotation`. Use authentic pseudonymous participant
IDs that identify the same person across both conditions, not one invented identity
per clip. Match labels to features by recording and question IDs. The blank
[template](../config/audio_delivery_labels.template.csv) deliberately has no fabricated
training rows.

The trainer rejects unknown participants, guessed labels, duplicate/augmented
answers, identity mismatches, shared recordings/checksums assigned to different
participants, silent recordings, invalid numeric features, or a fold missing one
class. At least `folds` participants in each class are needed for the configured
evaluation; this is a code prerequisite, not a sufficient sample size for a reliable
scientific claim.

## Run After Ground Truth Is Available

```bash
.venv/bin/python -m pip install -e '.[dev,ml]'
.venv/bin/audio-baseline \
  --features data/processed/delivery/samples.csv \
  --labels data/processed/delivery/labels.csv \
  --folds 3 \
  --out-dir data/models/delivery_run_001
```

The output directory must not exist. It contains `model.pkl` and aggregate
`metrics.json`; `data/models/` is ignored by Git. Only load trusted locally generated
pickle files. Keep staged participant data and derived model artifacts private. Do
not publish test-fixture accuracy as detector performance.

## Candidate Data and Remaining Validation

[Northwestern ALLSSTAR](https://speechbox.linguistics.northwestern.edu/allsstar)
contains scripted and spontaneous recordings. The complete local English ZIP has
1,163 WAV files, 963 TextGrids and 140 speakers. The first experiment uses `NWS`
reading and `ST1`/`ST2` picture-story speech; `QNA` is excluded until candidate-only
segmentation exists. Speaker codes provide grouping across recordings; 132
speakers have usable windows in both conditions. The
[SpeechBox site](https://speechbox.linguistics.northwestern.edu/) states CC BY 4.0
for its recordings, with attribution required. Raw recordings, local features
and model artifacts remain ignored by Git. See [ALLSSTAR processing](allsstar-audio.md).

Before training for the intended task, confirm the target, obtain matching labels,
and audit participant pairing, task differences, recording quality, language and
duration balance. Then evaluate on consented technical-interview pilots. Even a
validated reading detector does not establish AI use: humans can read their own
notes, while AI-assisted candidates may paraphrase rather than read.
