# Speech-to-Text Decision (pending approval)

**Status:** not chosen. The pipeline uses the provider-independent `Transcriber`
interface. Candidate adapters exist for evaluation only: `faster-whisper` and `whisperx`
(lazy imports; packages not installed by default; faster-whisper won't download weights
unless `allow_download=true`), plus a `hosted` placeholder that refuses to run without
explicit approval for external upload. None is wired in as a default.

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
| Setup complexity | Low (`pip install faster-whisper`) | Medium–high (PyTorch, HF token, pyannote licence) | Low code; needs an account, API key and billing |
| Fit for interview audio | Good transcripts; weak on disfluencies; no speaker separation | Best local option if speakers share a track | Best disfluency handling; privacy and cost trade-off |

Variant: **whisper.cpp** runs the same Whisper models with Apple-silicon GPU acceleration.
It has the same accuracy and filler behavior as faster-whisper, so it's an option if
CPU speed on a Mac becomes the bottleneck.

## Recommendation

1. **Default: faster-whisper, local** (`small` or `medium`, int8, CPU). It's free and
   private, and it gives word timestamps with the simplest setup.
2. **Avoid needing diarization:** record staged interviews with the candidate and the
   interviewer on separate audio tracks, or annotate `question_end`/`answer_start`.
   Then WhisperX is unnecessary.
3. **Decide with data, not opinion:** before committing, run a ~20-clip pilot on the
   public Michigan clips. They come with manual reference transcripts, including some
   fillers. Compare faster-whisper `small` vs `medium`, plus optionally one hosted API
   with filler preservation:

   ```bash
   interview-integrity stt-eval --reference <manual transcripts> --hypothesis <stt output> --report stt_pilot.json
   ```

   It reports corpus WER, filler recall and word-timestamp coverage. If filler recall
   from faster-whisper is too low for the filler features to be meaningful, reconsider a
   hosted API for **public** data only, and only if consent allows it for staged data.

## Benchmark readiness

`interview-integrity stt-benchmark` runs every candidate in
[config/stt_candidates.example.json](../config/stt_candidates.example.json) on the same
clips: streamed Michigan clips with human reference transcripts, or local
`--audio-dir/--reference-dir`. It reports:

| Factor | Measured by the benchmark | From the candidate config / this doc |
|---|---|---|
| WER / accuracy | `corpus_wer`, per-clip WER | |
| Word timestamps | `word_timestamp_coverage` | |
| Filler preservation | `filler_recall` | |
| Speaker separation | `speaker_label_coverage` | |
| Processing speed | `real_time_factor`, `model_load_seconds` | |
| Memory | `peak_process_rss_mb` | |
| Disk | | model download size (teammate measures `du -sh` of the model cache) |
| CPU/GPU | | device in the candidate options |
| Privacy | | `runs_locally`, `sends_audio_externally` (hosted is skipped unless approved) |
| Cost | | `cost_note` |

Not run yet: it needs model downloads. Commands are in
[teammate-validation.md](teammate-validation.md#4-stt-benchmark-downloads-models-several-gb).

## What approval is needed

- [ ] STT option (recommended: faster-whisper)
- [ ] Model size (recommended pilot: `small` and `medium`)
- [ ] Whether a hosted API may be tested on public Michigan audio (licence/terms check)
- [ ] Staged recording protocol: separate audio tracks per speaker (yes/no)
