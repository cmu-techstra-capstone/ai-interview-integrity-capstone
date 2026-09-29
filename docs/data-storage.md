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

## On-demand processing

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
