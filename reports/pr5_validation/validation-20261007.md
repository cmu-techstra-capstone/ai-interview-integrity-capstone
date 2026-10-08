# Docker and STT Validation on 7 October 2026

Docker build and all 205 tests now pass after local fixes. Three faster-whisper
configurations and WhisperX completed the same 20 Michigan clips with no failures. An audio-only
delivery trainer is implemented and tested, but no real delivery classifier has
been fitted. Staged pilot validation still requires recordings.

## Tests and Docker

| Check | Result |
|---|---|
| Native suite | 205 passed, 0 failed/errors/skipped; 5.167 seconds |
| Container suite | 205 passed, 0 failed/errors/skipped; 7.736 seconds |
| Image | `interview-integrity:dev`, Linux arm64, Python 3.12, extras `dev,ml` |
| Image size | 288,175,847 bytes (about 275 MiB), as reported by Docker inspect |
| Image ID | `sha256:6e0618527560661c2931ce9eefb5dbd8223a6b4c1007b939fbc2466d6e354575` |
| Container smoke tests | pipeline help, dataset status, STT list, audio-baseline help all exit 0 |

Evidence: [native JUnit](native-tests-20261007.xml),
[container JUnit](docker-tests-20261007.xml).

Initial container tests failed 3 checks because Dockerfile, .dockerignore and
compose.yaml were missing from the image. Explicit copies fix the failures without
copying raw data, weights or credentials. The isolated anonymous build command was:

```bash
docker --config .cache/docker-validation \
  --host unix:///Users/leio/.docker/run/docker.sock build \
  --build-arg EXTRAS=dev,ml --progress=plain -t interview-integrity:dev .
docker compose run --rm app pytest -q --junitxml=/app/data/docker-tests-20261007.xml
```

The default builder initially stalled during registry resolution. An isolated
configuration succeeded; no global Docker login or proxy settings were changed.
The exact cause of the initial delay was not established.

## STT Results

Input selection follows the existing guide's `--limit 20`: `trial_lie_001` through
`trial_lie_020`. These are all deceptive courtroom clips, not a balanced interview
sample. Total audio is 545.51 seconds with 1,525 reference words and just 9 standard
filled-pause tokens recognized by the project's tokenizer.

| Local CPU int8 candidate | Completed | Corpus WER | Filler recall | Word timestamp coverage | Reported RTF | Peak RSS MiB |
|---|---|---|---|---|---|---|
| faster-whisper small | 20/20 | 0.1534 | 0/9 | 1.0 | 0.142 | 1217.0 |
| faster-whisper medium | 20/20 | 0.1593 | 0/9 | 1.0 | 0.690 | 2043.6 |
| small with disfluency prompt | 20/20 | 0.1462 | 8/9 | 1.0 | 0.380 | 968.4 |
| WhisperX small aligned | 20/20 | 0.1711 | 0/9 | 1.0 | 0.188 | 1779.5 |

JSON evidence: [small](stt_small_cpu.json), [medium](stt_medium_cpu.json),
[prompted small](stt_small_prompt_cpu.json), [WhisperX](stt_whisperx_cpu.json).
Each candidate runs in its own process,
but some jobs overlapped on the CPU. RTF values are diagnostic observations, not
controlled speed comparisons. Model loading/download time is separate from RTF;
WhisperX's first successful alignment load is included in clip timing.

The prompted model emitted 25 standard filler tokens, with only 8 matching reference
counts under the evaluator's per-clip count matching rule. That is an approximate
count precision of 0.32, not a word-aligned event precision. High filler recall alone
therefore does not justify selecting the prompt for disfluency features. Timestamp
coverage means timestamps exist, not that their boundaries are accurate. Diarization
was disabled and speaker coverage is 0; hosted upload was never enabled.

## Reproduced Issues and Fixes

| Issue | Local change |
|---|---|
| faster-whisper 1.2.1 with PyAV 19.0.1 fails all decoding on removed `metadata_errors` argument | Bound the faster-whisper extra to `av>=11,<19`; verified PyAV 18.1.0 |
| Benchmark marks all failed clips as `ok` | Report `failed`/`partial`, attempted and failed counts; added regression tests |
| Docker tests cannot find configuration files | Copy only required configuration files; assert the copy rule |
| WhisperX reloads alignment weights for every clip | Cache alignment model by language; regression assertion checks one load for two clips |

Original failure JSON files are preserved. In particular,
`stt_small_cpu_av19_failure.json` still contains the old erroneous `ok` status with
zero successful clips. Do not interpret that legacy status as success.

WhisperX is isolated in `.venv-whisperx` because its PyTorch/transformers dependencies
differ from faster-whisper. It hit Python certificate-download failures for alignment
weights and NLTK data. Official alignment weights were downloaded with curl's verified
TLS and the retry uses certifi's trusted CA bundle via scoped `SSL_CERT_FILE`;
certificate verification has not been disabled. All 20 clips completed after the
CA/NLTK fix. A TorchCodec/FFmpeg 9 library warning remains, but did not prevent this
waveform-based benchmark from completing; diarization was not tested.

For the successful WhisperX retry, NLTK `punkt_tab` was downloaded into
`.cache/nltk_data`, then the command used scoped environment variables:

```bash
PATH="/opt/homebrew/bin:$PATH" \
SSL_CERT_FILE="$PWD/.venv-whisperx/lib/python3.13/site-packages/certifi/cacert.pem" \
NLTK_DATA="$PWD/.cache/nltk_data" HF_HOME="$PWD/.cache/whisperx-hf" \
TORCH_HOME="$PWD/.cache/models/torch" \
.venv-whisperx/bin/interview-integrity stt-benchmark \
  --candidates config/stt_whisperx_cpu.json --dataset michigan_deception --limit 20 \
  --cache-dir .cache/pr5-stt-whisperx --report reports/pr5_validation/stt_whisperx_cpu.json
```

The other three configurations are in `config/stt_small_cpu.json`,
`config/stt_medium_cpu.json` and `config/stt_small_prompt_cpu.json`, run independently
with `.venv/bin/interview-integrity` and the same dataset/limit. The validated native
environment uses Python 3.13.7, faster-whisper 1.2.1, CTranslate2 4.8.2, PyAV 18.1.0
and scikit-learn 1.9.1. The isolated WhisperX environment uses WhisperX 3.8.6,
PyTorch/torchaudio 2.8.0 and transformers 4.57.6.

## Audio Model State

The optional `audio-baseline` CLI uses 14 audio features, median imputation,
standardization, Logistic Regression and participant-grouped cross-validation.
Eight synthetic tests verify training mechanics and label/leakage safeguards. Details:
[audio-baseline.md](../../docs/audio-baseline.md).

Michigan data remains available for a truthful/deceptive classification exercise,
but no reading/spontaneous or AI-use labels were invented. No classifier trained on
real target data is available. Staged pilot validation still requires recordings;
none were provided. Restricted datasets were not downloaded and no email-based
dataset access request was submitted.
