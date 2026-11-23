# Speech-to-Text Decision

**Status (2026-11-01):** **faster-whisper `small` / CPU / INT8** is approved as the
project's **optional offline STT baseline** when explicitly selected. It is **not**
auto-applied to every recording, **not** a final production lock, and **not** a
scoring / AI-assistance model.

The pipeline still uses the provider-independent `Transcriber` interface. Without
`--stt` / an explicit transcriber / a sidecar transcript, processing continues with
energy VAD and null linguistic features.

## Approved optional baseline

| Setting | Value |
|---|---|
| Adapter / registry names | `faster-whisper-small-int8` (locked baseline) or `faster-whisper` (same defaults, overridable) |
| Model size | `small` |
| Device | `cpu` |
| Compute type | `int8` |
| Word timestamps | `true` |
| Downloads | **off** unless `allow_download=true` |
| Optional install | `pip install -e ".[stt-faster-whisper]"` (teammate machine; pins `av>=11,<19`) |
| Config file | [config/stt_baseline.faster_whisper_small_int8.json](../config/stt_baseline.faster_whisper_small_int8.json) |

```bash
# Sidecar transcript (preferred when available) — STT not used
interview-integrity process --video rec.mp4 --metadata rec.metadata.json --transcript rec.transcript.json

# No transcript, no STT — VAD-only timing, null linguistic features
interview-integrity process --video rec.mp4 --metadata rec.metadata.json

# Explicit optional baseline (requires package + local weights or allow_download on a large disk)
interview-integrity process --video rec.mp4 --metadata rec.metadata.json \
  --stt faster-whisper-small-int8 \
  --stt-option allow_download=true
```

From Python: `services.resolve_transcriber(stt="faster-whisper-small-int8", stt_options={...})`.

**Local validation on the constrained laptop:** mocked unit tests only. Live weight
download and inference were **not** run here. Teammate procedure:
[teammate-validation.md](teammate-validation.md#4-stt-benchmark-downloads-models-several-gb).

Leo's 20-clip Michigan benchmark (research branch) reported corpus WER ≈ 0.153 for
unprompted small INT8; that subset does not approve interview-domain accuracy or
filler quality. Hosted STT and WhisperX remain unapproved.

## Why STT matters for this project

| Need | Used by |
|---|---|
| Word-level timestamps | pauses, speech segments, `speech_rate_cv`, answer start and response latency, splitting a recording into answers |
| Filler preservation ("um", "uh") | `filler_word_count`, `self_correction_count`; disfluency is a key spontaneous-vs-read signal |
| Speaker separation | only needed if the interviewer and candidate share one audio track |
| Privacy | staged recordings are personal data covered by consent/IRB |

## Comparison

| Factor | faster-whisper (local) | WhisperX (local) | Hosted API (Deepgram / AssemblyAI / OpenAI) |
|---|---|---|---|
| Transcript accuracy | Whisper-level; good on clear English. `small` < `medium` < `large-v3` | Same as faster-whisper (uses it) | Generally strong; varies by vendor and model |
| Word timestamps | Yes; approximate (from attention alignment) | Yes; more precise (forced alignment with wav2vec2) | Yes (all three offer word timestamps) |
| Filler preservation | Weak: Whisper tends to drop "um/uh"; prompting helps only partially | Weak (aligns only the words Whisper outputs) | Deepgram and AssemblyAI have explicit filler/disfluency options; OpenAI's behavior is Whisper-like |
| Speaker separation | No | Yes (pyannote; needs a Hugging Face token and accepting the model terms) | Deepgram and AssemblyAI: yes. OpenAI: check current models |
| CPU requirement | Runs on a laptop CPU (int8). `small`/`medium` are practical; `large-v3` is slow | Works on CPU but slow, especially alignment and diarization | None locally |
| GPU requirement | Optional (NVIDIA CUDA only; **no Apple GPU acceleration**) | Recommended (CUDA) | None |
| Disk | Model only: ~0.5 GB (`small`), ~1.5 GB (`medium`), ~3 GB (`large-v3`) | PyTorch + models: several GB | None |
| Privacy | Audio never leaves the machine | Audio never leaves the machine | Audio sent to a third party; check consent wording, vendor retention terms and CMU policy |
| Cost | Free | Free | Pay per audio minute (check current pricing) |
| Setup complexity | Low (`pip install` optional extra) | Medium–high (PyTorch, HF token, pyannote licence) | Low code; needs an account, API key and billing |
| Project status | **Optional approved baseline** (`small` / CPU / INT8) | Candidate only; not approved | Placeholder; blocked without explicit upload approval |

Variant: **whisper.cpp** runs the same Whisper models with Apple-silicon GPU acceleration.
It has the same accuracy and filler behavior as faster-whisper, so it's an option if
CPU speed on a Mac becomes the bottleneck — **not selected**.

## Still open (not approved by the baseline decision)

- [x] Initial STT option: faster-whisper small / CPU / INT8 (optional, explicit)
- [ ] Final production STT lock / model-size change after staged-interview evaluation
- [ ] Whether a hosted API may be tested on public Michigan audio (licence/terms check)
- [ ] Staged recording protocol: separate audio tracks per speaker (yes/no)
- [ ] Diarization (WhisperX / pyannote / hosted) — avoid if separate tracks or metadata windows exist
