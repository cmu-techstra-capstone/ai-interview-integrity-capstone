# Data Storage and Acquisition

```text
Google Drive (shared)  = raw datasets + processed outputs
GitHub                 = code, configs, manifests, docs, tiny test fixtures
Laptop                 = temporary, size-bounded cache only (default limit 500 MB)
```

## Shared folder layout

Root folder: **`AI Interview Integrity Capstone/`**

```text
AI Interview Integrity Capstone/
├── datasets/
│   ├── dolos/
│   ├── michigan_deception/
│   ├── bag_of_lies/
│   └── staged_interviews/
├── processed/
│   ├── transcripts/<dataset>/<video_id>.json
│   ├── audio_features/<dataset>/<video_id>.json
│   ├── linguistic_features/<dataset>/<video_id>.json
│   └── combined_features/<dataset>/<video_id>.json
├── metadata/
└── docs/
```

`interview-integrity storage-init --root <shared root>` creates any missing folders. It never
deletes or overwrites existing content.

## Manifests (in Git)

- `manifests/datasets.json`: one entry per dataset with the official URL, access type,
  license summary, approximate size, Drive folder, status, and manual access steps.
- `manifests/files/<dataset>.csv`: one row per raw file. `drive_location` is relative to
  the shared root. Key columns: `dataset_name, video_id, participant_id, deception_label,
  assistance_label, drive_location, transcript_location, remote_reference, file_status,
  local_cache_path, size_bytes, crc32`.
- `file_status` is one of `AVAILABLE_AT_SOURCE`, `ACCESS_PENDING`, `IN_DRIVE`,
  `PROCESSED`, `MISSING` or `ERROR`.
- For DOLOS, Michigan and Bag-of-Lies, `assistance_label` is always `UNKNOWN`. Loading
  a manifest that says otherwise fails validation.

## Acquisition

| Dataset | Access | How it gets into Drive |
|---|---|---|
| Michigan Real-life Deception | Public | `interview-integrity datasets acquire michigan_deception --root <shared root>` streams each clip and transcript from the official zip, using HTTP range requests, straight into the Drive folder. The ~249 MB archive is never saved locally. Resumable. Sizes and CRC32 are verified. |
| DOLOS | ROSE Lab Release Agreement | Manual request (see `manifests/datasets.json`). After approval, put files in `datasets/dolos/` and add manifest rows. |
| Bag-of-Lies | Signed institutional license | Manual (see `manifests/datasets.json`). The 6.14 GB archive is delivered via Google Drive. Copy it Drive-to-Drive; never pull it through a laptop. |

Use `--limit N` for a small trial run first. `interview-integrity datasets status` shows
where each dataset stands.

## Processing straight from the official source (no Drive needed)

For public datasets whose official archive supports HTTP range requests (Michigan):

```bash
interview-integrity process-source --dataset michigan_deception [--limit N] [--force]
```

```text
official zip ──range request──▶ one clip in TemporaryCache ──▶ pipeline ──▶ processed/ (in Git)
                                        └── deleted after each clip
```

`ArchiveSourceStorage` presents the archive as read-only storage. Rows record the source
as `<zip url>#<member>`. Already-processed clips are skipped unless you pass `--force`.

## On-demand processing from shared storage

```text
Drive raw video (+ transcript) → TemporaryCache (≤ 500 MB, checked before download)
  → ingestion → audio extraction → transcript → features
  → JSON outputs uploaded to processed/ → temp cache deleted (also on failure)
```

```bash
interview-integrity process-remote --dataset michigan_deception --root <shared root> --limit 5
```

This updates `file_status` to `PROCESSED` in the manifest. It also appends rows to the
local `data/processed/samples.jsonl` (gitignored) for quick analysis.

## Storage backends

Code talks to `storage.remote.RemoteStorage`. Today only `LocalFolderStorage` exists. It
works with any mounted folder, including a **Google Drive for Desktop** mount such as:

```text
~/Library/CloudStorage/GoogleDrive-<account>/My Drive/AI Interview Integrity Capstone
```

A native backend (rclone or the Drive API) is pending decision **D6** in
`docs/decisions.md`. The interface already has `upload_stream`, which maps directly to
`rclone rcat` or a Drive API resumable upload.

## Rules

- Never commit media, audio, archives or dataset files. `.gitignore` blocks common
  extensions and credential files.
- Don't bypass access controls. Restricted datasets stay `ACCESS_PENDING` until the team
  completes the manual step.
- Respect each license: no redistribution, and cite the dataset papers.

## Access status (verified 2026-10-03)

```text
Dataset:              University of Michigan Real-life Deception
Official source:      https://web.eecs.umich.edu/~mihalcea/downloads.html
Required action:      none (public download)
License/access:       no licence file; research use; cite Pérez-Rosas et al. (ICMI 2015)
What we can do now:   done: all 121 clips processed from source; features in processed/

Dataset:              DOLOS (ROSE Lab, NTU)
Official source:      https://rose1.ntu.edu.sg/dataset/DOLOS/
Required action:      create a ROSE Lab account (CMU email) → "Request" → accept the Release Agreement → wait for approval
License/access:       academic, non-commercial only; no redistribution or derived datasets without permission
What we can do after: store clips in private shared storage, add manifest rows, run process-remote
                      (1,675 clips, 213 participants: real participant IDs make leakage-safe splits possible)

Dataset:              Bag-of-Lies (IIIT-Delhi)
Official source:      http://iab-rubric.org/index.php/bag-of-lies
Required action:      licence agreement signed by someone with legal authority for CMU (e.g. via advisor /
                      Office of Sponsored Programs), emailed to databases@iab-rubric.org,
                      subject "License agreement for Bag-of-Lies Database"
License/access:       research/educational only; no commercial use; no User_12 data in publications; cite paper
What we can do after: copy the 6.14 GB archive Drive-to-Drive, add manifest rows, process on a machine with disk space
```

All three provide **deception** labels only; `assistance_label` stays `UNKNOWN`.
