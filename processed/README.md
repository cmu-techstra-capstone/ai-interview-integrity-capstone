# Processed features (committed)

Lightweight outputs derived from public datasets. **No raw video or audio is stored in this
repository.** Clips are streamed one at a time from the official source into a temporary
cache, processed, and deleted.

| Path | Contents |
|---|---|
| `combined_features/<dataset>.csv` | One row per clip: IDs, labels, transcript, all features. **Start here.** |
| `combined_features/<dataset>/<video_id>.json` | The same row, per clip |
| `linguistic_features/<dataset>/<video_id>.json` | Linguistic subset |
| `audio_features/<dataset>/<video_id>.json` | Timing subset |
| `transcripts/<dataset>/<video_id>.json` | Transcript in the project's standard format |
| `quality/<dataset>.json` | Quality report (`interview-integrity quality`): errors/warnings per clip |

```python
import pandas as pd
df = pd.read_csv("processed/combined_features/michigan_deception.csv")
```

Regenerate (about 3 minutes; streams ~300 MB but holds at most one clip locally):

```bash
interview-integrity process-source --dataset michigan_deception --force
```

## michigan_deception

- Source: Real-life Deception Detection dataset, University of Michigan
  (https://web.eecs.umich.edu/~mihalcea/downloads.html). 121 courtroom clips
  (61 `DECEPTIVE`, 60 `TRUTHFUL`).
- Cite: Pérez-Rosas, Abouelenien, Mihalcea, Burzo. *Deception Detection using Real-life
  Trial Data.* ICMI 2015.
- `assistance_label` is `UNKNOWN` for every row. These are deception labels, not
  AI-assistance labels.
- Transcripts are the dataset's manual transcripts. They have no word timestamps, so
  timing features come from energy-based VAD (`timing_source = energy_vad`).
- The dataset has no speaker IDs. `participant_id` is `unknown:<video_id>`, so
  participant-grouped splits cannot prevent the same speaker appearing in two splits.
- VAD caveat: courtroom background noise can count as speech, so pause counts are
  likely undercounted and speech duration overcounted.
- Quality report: 0 errors, 15 warnings (6 noisy, 5 clipped, 4 extreme speech rate).
  Check `quality/michigan_deception.json` before using a clip's timing features.
- Outputs were generated before the `audio_duration` column existed. Regenerate with
  `process-source --force` on a machine with bandwidth (docs/teammate-validation.md §3).
- Columns `video_path`/`audio_path` were renamed `video_reference`/`audio_reference`.
  Loaders still accept the old names.

Only public-dataset outputs belong here. Staged-interview outputs contain participant
transcripts and must stay in private shared storage (enforced by `.gitignore`).
