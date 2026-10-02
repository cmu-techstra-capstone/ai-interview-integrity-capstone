# Audio and Timing Features

All times are in seconds. Values that can't be measured are `null`. Code lives in
[features/timing.py](../src/interview_integrity/features/timing.py),
[features/loudness.py](../src/interview_integrity/features/loudness.py),
[audio/vad.py](../src/interview_integrity/audio/vad.py) and
[audio/quality.py](../src/interview_integrity/audio/quality.py).

**Speech intervals** are the basis for most of these features. They come from word
timestamps when the transcript has them (`timing_source=word_timestamps`). Otherwise they
come from adaptive energy VAD (`timing_source=energy_vad`): 30 ms frames count as speech
when they're within 25 dB of the answer's 95th-percentile level. No speech is reported
if the level barely varies. Gaps under 0.3 s are bridged.

## Inventory

| Feature | Implemented | Input required | Calculation | Known limitations |
|---|---|---|---|---|
| `answer_duration` | ✅ | answer window from metadata, or detected speech | `answer_end − answer_start` | Without metadata, spans first-to-last detected speech after `question_end` (or from 0) |
| `speech_duration` | ✅ | audio, or word timestamps | sum of speech intervals inside the window | VAD counts loud background noise as speech |
| `silence_duration` | ✅ | as above | `answer_duration − speech_duration` | as above |
| `pause_count` | ✅ | as above | gaps ≥ 0.3 s between speech intervals | VAD undercounts pauses in noisy audio |
| `long_pause_count` | ✅ | as above | pauses ≥ 1.0 s | as above |
| `mean_pause_duration`, `max_pause_duration`, `total_pause_duration`, `pause_duration_std`, `pause_ratio` | ✅ | as above | stats over pauses; ratio = total / answer duration | `null` (mean/max) or 0 when there are no pauses; std needs ≥ 2 pauses |
| `speech_segment_count`, `mean_speech_segment_duration`, `speech_segment_duration_std` | ✅ | as above | stats over speech intervals | segment boundaries depend on the 0.3 s gap rule |
| `speech_rate_wpm` | ✅ | transcript + answer window | `60 × words / answer_duration` | needs a transcript; transcript must match the window |
| `articulation_rate_wpm` | ✅ | transcript + speech intervals | `60 × words / speech_duration` | inflated when VAD misses quiet speech |
| `speech_rate_cv` | ✅ (inactive) | **word timestamps** | coefficient of variation of words/s across segments with ≥ 3 words | `null` until an STT with word timestamps is chosen |
| `response_latency` | ✅ | `question_end` in metadata | `answer_start − question_end` | `null` without `question_end`; never estimated |
| `speech_level_mean_dbfs`, `speech_level_std_db`, `speech_level_range_db` | ✅ | audio | mean, std and p90−p10 of speech-frame RMS levels | absolute level depends on mic gain; std/range are more comparable |
| `audio_noise_floor_dbfs`, `audio_speech_level_dbfs`, `audio_snr_db`, `audio_peak_dbfs`, `audio_clipping_ratio` | ✅ | audio (whole recording) | p10 / p95 frame level, their difference, peak, share of full-scale samples | energy-only SNR estimate |
| `audio_is_silent`, `audio_is_noisy`, `audio_is_clipped` | ✅ | as above | peak < −60 dBFS; SNR < 15 dB; clipping > 1% | thresholds are simple and documented in `audio/quality.py` |

The quality report (`interview-integrity quality`) turns these into explicit errors and
warnings: silent audio, no speech, noisy or clipped recordings, extreme speech or
articulation rates, and invalid durations.

## Expansion plan

Goal: signals that may separate **spontaneous** answers from **read**, **unusually
prepared** or **AI-assisted** ones. None of these is evidence on its own.

### Already reliable (in the pipeline now)

Pause structure (count, long pauses, variability), speech/silence balance, segment
structure, speech rate, response latency (with `question_end`), loudness variation, and
recording quality. Why they may matter: read speech tends to have regular, short pauses
at phrase boundaries and fewer long hesitations. Looking something up tends to produce
long pauses or long latency.

### Feasible next (no model or provider decision)

| Feature | Why | Blocker |
|---|---|---|
| Within-participant normalization (z-score each feature against the same participant's `HUMAN_UNASSISTED` answers) | removes individual speaking style, which is critical for staged data | none; needs staged data |
| Latency normalized by question length | long questions naturally take longer to answer | none |
| Pitch (F0) mean/std/range, intonation flatness | reading aloud often has flatter intonation | needs a numeric dependency (numpy, or Praat-parselmouth/librosa); pure Python is too slow. **Approval needed for the dependency**, not a model |
| Pause placement vs clause/sentence boundaries | read pauses fall at punctuation, spontaneous ones mid-clause | needs word timestamps (STT decision) |
| Speech-rate drift (start vs end of answer), `speech_rate_cv` | reading keeps an even pace | needs word timestamps (STT decision) |
| Filled-pause timing and rate from audio-aligned transcript | disfluency marks spontaneous speech | needs an STT that keeps fillers |

### Requires research or a model decision (documented only, not implemented)

| Capability | Options | Notes |
|---|---|---|
| Speaker diarization | WhisperX/pyannote, hosted STT diarization | avoidable if staged recordings use separate tracks |
| Background typing / screen-reading sounds | audio-event models (e.g. YAMNet, PANNs) | relevant for "looking up an answer"; needs validation |
| Second voice / whispered prompting | diarization or audio-event models | relevant, high false-positive risk |
| Acoustic disfluency detection (independent of STT) | dedicated disfluency models | research-grade |
| Learned prosody / speech embeddings | wav2vec2, HuBERT, WavLM | opaque; reduces explainability |
| Emotion / stress recognition | various models | weak validity for this task; not recommended |
| Read-vs-spontaneous classifier | trained model | this is modelling work; needs approval |
