# Heavy Validation (teammate machine)

These checks need disk space, network bandwidth or model downloads, so they were **not**
run on the development laptop. Run them on a machine with ≥ 20 GB free. Report results
back in the PR, using the "Report" line under each step.

```bash
git clone https://github.com/cmu-techstra-capstone/ai-interview-integrity-capstone.git
cd ai-interview-integrity-capstone
git checkout feature/docker-stt-staged-readiness
```

## 1. Native test suite (baseline)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```
Report: pass count (expected: all pass).

## 2. Docker build, tests, CLI smoke test

```bash
export HOST_UID=$(id -u) HOST_GID=$(id -g)      # Linux only
docker compose build
docker image ls interview-integrity:dev           # note the SIZE column
docker compose run --rm app pytest -q
docker compose run --rm app interview-integrity --help
docker compose run --rm app interview-integrity datasets status
docker compose run --rm app interview-integrity stt-list
```
Report: build success, image size, pytest pass count, any CLI errors.

## 3. Regenerate Michigan features (streams ~300 MB, keeps ~2 MB)

This adds the newer columns (e.g. `audio_duration`) to the committed outputs. Run it on
the host; the container may hit the TLS issue described in [docker.md](docker.md).

```bash
interview-integrity process-source --dataset michigan_deception --force
interview-integrity quality --input processed/combined_features/michigan_deception \
  --report processed/quality/michigan_deception.json
git status --short processed manifests            # expect only JSON/CSV changes, no media
```
Report: processed/failed counts, quality error/warning counts. Commit the updated
`processed/` and `manifests/` on a branch.

## 4. STT benchmark (downloads models: several GB)

Uses Michigan's human transcripts as the reference. Audio comes from the public source.
**Nothing is sent to hosted services** unless `--allow-external-upload` is passed, which
requires project approval.

```bash
pip install -e ".[dev,stt-faster-whisper]"        # add stt-whisperx to include WhisperX
interview-integrity stt-benchmark \
  --candidates config/stt_candidates.example.json \
  --dataset michigan_deception --limit 20 \
  --report stt_benchmark_michigan.json
```

For a clean memory figure per candidate, run one candidate per process: copy the config
with a single entry. For WhisperX diarization, add `"diarize": true, "hf_token": "<token>"`
to its options. That needs a Hugging Face account with the pyannote model terms accepted.

Report: for each candidate, `corpus_wer`, `filler_recall`, `word_timestamp_coverage`,
`speaker_label_coverage`, `real_time_factor`, `peak_process_rss_mb`, model download size
(`du -sh ~/.cache/huggingface`). Attach `stt_benchmark_michigan.json`.

## 5. Staged pilot dry run (once 2–3 pilot recordings exist)

Keep pilot media in private storage, never in Git. Folder layout (`<name>` is free):

```text
pilot/
  STG-P001-S01.mp4
  STG-P001-S01.metadata.json      # from 'staged template', timestamps from 'staged import-labels'
  STG-P001-S01.transcript.json    # optional (else --stt candidate, else no linguistic features)
```

```bash
interview-integrity staged validate pilot/*.metadata.json
interview-integrity process-batch --dir pilot --out-dir data/pilot_out \
  [--stt faster-whisper --stt-option model_size=small --stt-option allow_download=true]
interview-integrity quality --input data/pilot_out/samples.jsonl -v
interview-integrity split --input data/pilot_out/samples.jsonl
```
Report: validation output, processed/failed recordings, quality summary. **Don't share
transcripts or the outputs publicly.**

## 6. Cleanup afterwards

```bash
interview-integrity cache-clean                    # stale temp caches from killed runs
docker builder prune                               # build cache
docker image rm interview-integrity:dev            # if no longer needed
```
