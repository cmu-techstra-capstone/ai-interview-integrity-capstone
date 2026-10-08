# ALLSSTAR audio baseline

ALLSSTAR supports research on read versus spontaneous speech. The complete English
ZIP was downloaded manually and imported locally on 2026-10-07. The first
audio-only baseline uses NWS/ST1/ST2 and achieved 0.739 out-of-fold balanced
accuracy under five-fold speaker-separated evaluation. It classifies delivery
mode, not AI assistance. See the [first experiment report](../reports/allsstar/first-run-20261007.md)
for counts, errors and limitations.

The [VAD/prosody follow-up](../reports/allsstar/prosody-vad-20261007.md) reuses
exactly these windows and folds; its Silero/prosody SVM reduces FPR to 12.3%.
This remains an exploratory delivery-mode result, not interview or AI-use validation.

## Corpus and labels

The official selector reported 1,163 English WAV files, 963 TextGrids, 140
speakers, 42.02 hours and 9.95 GB. The local ZIP inventory confirms the WAV,
TextGrid and speaker counts, and full-archive CRC validation passed. Duration and
the selector's size remain catalog statistics; the ZIP is 10,615,555,746 bytes
(9.89 GiB). Files may contain multiple utterances, so file counts are not
counts of independent answers. All-language ALLSSTAR totals were 1,976 WAV files
and 1,345 TextGrids.

| Task | English WAV files | Delivery label | Initial experiment |
|---|---:|---|---|
| HT1 | 139 | READING | Excluded: sentence-reading protocol differs from continuous passage |
| HT2, DHR, LPP | 140 each | READING | Excluded initially; possible task-transfer tests |
| NWS | 140 | READING | Included |
| ST1, ST2 | 139 each | SPONTANEOUS | Included |
| ST3, ST4 | 23 each | SPONTANEOUS | Excluded initially: narrower speaker coverage |
| QNA | 140 | SPONTANEOUS | Excluded: candidate-only segmentation not implemented |

Source: [ALLSSTAR](https://speechbox.linguistics.northwestern.edu/allsstar),
[official selector](https://speechbox.linguistics.northwestern.edu/ALLSSTARcentral/#!/recordings).
The counts were queried through the selector's public inventory and statistics
service. The local importer checked file counts, speaker-code consistency,
duplicate filenames and archive integrity before training. Do not publish expiring download
links, email addresses or recordings in the repository.

Labels follow elicitation tasks, not judgments based on fluency. NWS is reading;
ST1/ST2 are picture-story elicitation. These labels are neither truthful/deceptive
nor AI-assisted/unassisted. The initial selected tasks cover at most 418 source
recordings (140 + 139 + 139), before failed decoding, short or silent windows.
The completed first import retained 862 windows from 408 recordings and 140
speakers: 148 reading and 714 spontaneous. Ten recordings were too short for a
complete window, two windows were silent or lacked separable speech, and no
recording failed decoding. Five retained windows have a noise warning.

## Local import

Keep the original ZIP under ignored `data/raw/allsstar/`. Reserve approximately
25–30 GB if retaining both archive and unpacked files; the importer can read a ZIP
one selected recording at a time without retaining an unpacked copy. Temporary
audio is deleted after feature extraction. Do not load models supplied inside an
archive, and do not execute any downloaded scripts.

From the repository root, use the existing environment:

```sh
.venv/bin/python -m interview_integrity.modeling.allsstar \
  --source data/raw/allsstar/english-full.zip \
  --out-dir data/processed/allsstar/delivery-first-run \
  --expect-wav 1163 --expect-textgrid 963 --expect-participants 140 \
  --tasks NWS ST1 ST2 --window-seconds 30 --max-windows 4 --workers 2
```

Use the actual ZIP name. An extracted directory is also accepted. New output
directories are required; existing runs are never overwritten. Corpus-count
mismatches stop the import before processing. ZIP member paths, duplication,
symlinks and expansion sizes are validated, and every member's CRC is checked
before processing an archive. Task and speaker codes are parsed from WAV names;
unexpected formats or conflicting speaker metadata fail closed.

Audio is converted temporarily to 16 kHz mono PCM. Each recording contributes at
most four consecutive, nonoverlapping, complete 30-second windows. Short tails
are discarded, rather than padded or admitted at class-dependent lengths.
Silent windows and windows without separable energy-based speech are excluded.
Noisy/clipped flags are recorded for review, not used as classifier features.
This baseline does not separate different speakers inside a recording.

Outputs, all under the ignored run directory:

- `inventory.json`: original recording identities and task metadata.
- `features.jsonl`: fixed-window timing and loudness features.
- `labels.csv`: task-derived READING/SPONTANEOUS labels and stable pseudonymous IDs.
- `quality.json`: inventory, accepted/excluded counts and decoding failures.

An import with failures or without both usable classes exits nonzero. Check
`quality.json` and listen to a consent/licence-compatible small sample of each
task before interpreting energy-VAD intervals as speaker behavior. The initial
window and sampling settings are engineering starting points, not validated
optimal thresholds.

## Training after a successful real import

```sh
.venv/bin/python -m interview_integrity.modeling.audio_baseline \
  --features data/processed/allsstar/delivery-first-run/features.jsonl \
  --labels data/processed/allsstar/delivery-first-run/labels.csv \
  --out-dir data/models/allsstar-delivery-first-run \
  --folds 5 --seed 42
```

The trainer uses 14 audio-only timing/loudness features, median imputation,
standardization and class-balanced Logistic Regression. Imputation and scaling
are fitted inside each training fold. No ASR, transcripts, demographics, task
identifiers, raw recording lengths or microphone gain are classifier inputs.
Pitch/F0 and neural audio embeddings are not included in this first experiment.

All recordings and windows from a speaker stay in the same evaluation fold.
Scores are window-level out-of-fold balanced accuracy, reading-class F1,
ROC-AUC and a confusion matrix, with a majority-class baseline. Windows are
correlated, so they must not be treated as independent people when estimating
uncertainty. A final model refit on all imported rows is distinct from the
out-of-fold evaluation models.

## Limits and subsequent checks

Task content, picture-story demands, leading silence and recording procedure may
explain performance without indicating a general reading cue. Even with speaker
separation, this experiment cannot establish transfer to interviews or unseen
tasks. Inspect VAD errors and task artifacts, then evaluate held-out tasks and
speaker-clustered uncertainty. Review performance across available language
backgrounds without using those metadata as predictor inputs.

More recordings from the same speakers do not add independent speakers. The
training results must remain research delivery-mode results, not AI-use or
cheating probabilities. Technical interviews with consented controlled reading
and spontaneous conditions are still required for domain validation.
