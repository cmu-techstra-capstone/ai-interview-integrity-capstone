# Audio VAD and Prosody Experiment

This optional research workflow compares voice activity detection (VAD) and
prosody features for reading versus spontaneous speech. It preserves the original
ALLSSTAR cohort and speaker-separated folds. It does not perform ASR, detect AI
use, or change the default interview-processing pipeline.

## Feature groups

| Group | Audio features | Count |
|---|---|---:|
| energy | Original energy-VAD timing and loudness | 14 |
| silero | Same timing and loudness definitions, using Silero speech intervals | 14 |
| energy_prosody | Original features plus selected eGeMAPS descriptors | 34 |
| silero_prosody | Silero features plus selected eGeMAPS descriptors | 34 |

The 20 prosody descriptors cover F0 variability/range/rising/falling slopes,
loudness variability/range, jitter, shimmer, harmonic-to-noise ratio and
voiced/unvoiced segment summaries. The list is fixed in
`features/prosody.py` before evaluation. Absolute F0 means/percentiles, absolute
microphone level, MFCCs, transcripts, demographics, identities and task codes are
not predictor inputs. Removing explicit demographic inputs does not remove
speaker or language bias from acoustic features.

Selected eGeMAPS descriptors are computed over the same complete window in both
prosody groups; the VAD mask does not alter that extraction. Missing/nonfinite
statistics become null and are imputed within each training fold.

## Local dependencies and command

```sh
.venv/bin/python -m pip install -e '.[dev,audio-research]'

.venv/bin/python -u -m interview_integrity.modeling.audio_experiment \
  --source data/raw/allsstar/english-full.zip \
  --base-dir data/processed/allsstar/delivery-first-run \
  --out-dir data/processed/allsstar/prosody-vad-20261007 \
  --model-dir data/models/allsstar-prosody-vad-20261007
```

Choose new output directories for subsequent runs; existing experiments are never
overwritten. Raw media, listening samples, per-speaker predictions and model
artifacts remain in ignored local directories. No remote inference or audio
upload occurs. Silero uses the ONNX weights bundled in its installed package;
ONNX telemetry is disabled by the adapter. Heavy packages are imported only when
the optional workflow runs, not by the standard pipeline or CLI help.

[Silero VAD](https://github.com/snakers4/silero-vad) supplies the speech detector.
[openSMILE eGeMAPSv02](https://audeering.github.io/opensmile-python/usage.html)
supplies the prosody descriptors. Review
[openSMILE licensing](https://audeering.github.io/opensmile-python/#license)
before commercial integration; the academic experiment does not establish
permission for use in a customer product.

## Paired processing and evaluation

The source WAV checksum must match the original baseline. Only the old NWS/ST1/ST2
windows are processed: no cohort expansion, padding, shorter windows, silence
trimming or noise-based exclusions. All original energy features are recomputed
and must match exactly. Any failed recording or incomplete cohort blocks training
comparisons instead of silently reporting a smaller sample as improvement.

Silero runs at 16 kHz, threshold 0.5, minimum speech 100 ms, minimum silence 300 ms
and zero padding, with recurrent state reset per window. The old energy detector
uses a 300 ms merge gap and 100 ms minimum segment. These policies are comparable
but not algorithmically identical. No-speech detections are reported and retained
in the paired cohort; they are not treated as proof that the source is silent.

Each feature group uses class-balanced Logistic Regression (C=1, max_iter=2000)
and RBF SVM (C=1, gamma=scale). Median imputation and standardization fit inside
each fold. Five-fold StratifiedGroupKFold uses seed 42 and stable speaker IDs;
row-by-row fold assignments must match across all eight arms. Thresholds remain
at classifier defaults and there is no hyperparameter search. SVM decision margins
are not probabilities; neither classifier's scores are cheating confidence.

Out-of-fold balanced accuracy, reading precision/recall/F1, ROC AUC and the
spontaneous-to-reading false-positive rate are reported. Each final pipeline is
refitted on all rows after evaluation. These are exploratory comparisons on
previously examined folds, not independent confirmation of the best model.
Interview-domain and held-out task evaluation remain necessary.

## Private listening audit

The feature output includes `audit/index.html`, 20 targeted WAV examples and
`audit/human-review.csv`: ten strongest old-model false positives, five strongest
false negatives and five correct controls. Open the HTML locally to listen and
compare detected-speech timelines. This selection is not a representative sample.

Annotate whether speech boundaries, short pauses, background sounds or leading
silence were missed. Fill in the CSV's human-check status, preferred detector and
notes. The generated audit starts unchecked; automated VAD disagreement is not
an error measurement. TextGrid counts alone do not establish a usable VAD ground
truth, and no alignment labels are used by this workflow.

## Local recording prediction

`modeling/audio_predict.py` runs the fixed Silero/prosody RBF SVM on a new local
recording without training or ASR. Use only a trusted model produced by this
project: loading an untrusted pickle can execute arbitrary code.

```sh
.venv/bin/python -m interview_integrity.modeling.audio_predict \
  --audio data/raw/manual_audio/example.m4a \
  --trusted-model data/models/allsstar-prosody-vad-20261007/silero_prosody_svm_rbf/model.pkl \
  --out-dir data/processed/manual_audio/example-run \
  --expected SPONTANEOUS
```

Choose a new private output directory. Audio is converted to 16 kHz mono PCM;
only complete consecutive 30-second windows within the first 120 seconds are
used, matching training. Short tails are not padded. No speech or a silent
window produces an abstention; noisy/clipped flags remain separate from inputs.
The optional expected label is user-reported comparison metadata, never a
predictor. The CLI reports the SVM decision margin, not a probability. Positive
values favor reading, negative values favor spontaneous delivery.

Saved outputs include normalized audio, per-window features and predictions,
quality flags, source/model checksums, and a private Markdown report. Agreement
between windows is only a descriptive summary, not a validated recording-level
classifier. Personal tests may expose false positives but do not establish
population accuracy; training used English speech and transfer to other
languages remains unvalidated. Never publish personal recordings or reports.
