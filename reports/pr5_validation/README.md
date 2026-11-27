# PR 5 Native Tests and Michigan Validation

On 2026-10-06, the native test suite passed all 196 tests and Michigan regeneration
completed for all 121 clips with no processing failures. The regenerated outputs
contain `audio_duration` for every clip. Quality checks report 0 errors and 15 warnings
across 14 distinct clips. This validates the native processing path, not Docker, STT
accuracy, or an AI-assistance model.

## Environment

| Item | Value |
|---|---|
| Base commit | `6e9635cbaf3b5e23dfaa0cff00d0e355423aebf7` from `feature/docker-stt-staged-readiness` |
| Local validation branch | `codex/pr5-michigan-validation` |
| Platform | macOS 15.6.1, arm64 |
| Python | 3.13.7, isolated `.venv` |
| Dependencies | Editable `.[dev]` installation; pytest 9.1.1 |
| Media tools | Homebrew FFmpeg and FFprobe 9.0.2 |
| Model dependencies | No STT or model weights installed for this validation |

## Results

| Check | Result |
|---|---|
| Native tests | 196 passed, 0 failed, 0 errors, 0 skipped; 7.318 seconds |
| Single clip smoke run | 1 processed, 0 failed |
| Full source regeneration | 121 processed, 0 failed; CLI reported 308.0 MB fetched from source |
| Combined JSON and CSV | 121 rows in each; all have positive numeric `audio_duration` |
| Audio duration | 4.504–81.451 seconds per clip; 3,385.85 seconds total (about 56.4 minutes) |
| Deception labels | 61 `DECEPTIVE`, 60 `TRUTHFUL`; unchanged |
| AI assistance labels | All 121 `UNKNOWN`; unchanged |
| Timing and transcripts | All 121 use `energy_vad` and existing `sidecar` transcripts; no ASR run |
| Quality report | 0 errors; 6 noisy, 5 clipped, 4 extreme speech rate warnings |
| Cache and retained media | Processing cache empty; no raw media or archive files retained in project data/output directories |

Test evidence: [native-tests.xml](native-tests.xml).
Quality evidence: [michigan_deception.json](../../processed/quality/michigan_deception.json).

The noisy clip `trial_lie_048` also has an extreme speech rate warning, so 15 warning
instances correspond to 14 clips. Warnings are recording/feature quality indicators,
not evidence of cheating. No clip was removed during this validation.

## Reproduce

Run from the repository root after installing FFmpeg and FFprobe. On this macOS
machine, `/opt/homebrew/bin` must be on `PATH`.

```bash
export PATH="/opt/homebrew/bin:$PATH"
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q --junitxml=reports/pr5_validation/native-tests.xml
.venv/bin/interview-integrity process-source --dataset michigan_deception --force --limit 1 \
  --cache-dir .cache/pr5-michigan-validation
.venv/bin/interview-integrity process-source --dataset michigan_deception --force \
  --cache-dir .cache/pr5-michigan-validation
.venv/bin/interview-integrity quality --input processed/combined_features/michigan_deception \
  --report processed/quality/michigan_deception.json
```

## Output Changes

Regeneration changes 121 audio feature JSON files, 121 combined feature JSON files,
the combined CSV, and the quality JSON. Existing manifests, transcripts and linguistic
feature files remain unchanged. No application source code changed.

In addition to the new duration field, 21 combined rows differ in existing numeric
audio features compared with the base commit. Maximum absolute changes in checked
fields are 0.03 seconds for answer end and speech duration, 0.549 words/minute for
speech rate, 0.05 dB for SNR, and 0.00008 for clipping ratio. Labels, transcripts,
recording identifiers and source checksums remain unchanged. Cross-environment media
decoding is a possible explanation, not a verified cause; record the decoder version
when comparing regenerated features and avoid assuming bit-for-bit reproducibility.

## Limits and Remaining Work

Michigan contains courtroom deception clips, not controlled AI-assisted interviews
or labeled reading-versus-spontaneous speech. Its labels cannot train or evaluate the
intended AI-assistance classifier directly. All participant identifiers are unknown
placeholders, so a zero-error quality report does not establish speaker-independent
train/test splits. Word timestamps and question-end timestamps are unavailable;
`speech_rate_cv` and response latency remain null.

This run covers native tests and Michigan regeneration in
[teammate-validation.md](../../docs/teammate-validation.md), sections 1 and 3 only.
Docker build/container tests, the 20-clip STT benchmark, staged pilots, and audio model
training remain pending. Test-suite success does not resolve previously identified
PR review findings.

For audio modeling, use these outputs to validate loading and feature selection;
obtain matching ground-truth labels before claiming reading or AI-assistance
detection performance. Keep recording-quality variables separate from behavioral
model inputs and do not create participant-independent splits from the placeholders.
