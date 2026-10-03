# Evidence Contract

The shape every future audio, transcript and visual signal must take for human review.
Defined in [src/interview_integrity/evidence.py](../src/interview_integrity/evidence.py).
**This contract does not decide which signals indicate AI assistance, how to combine
them, or any score.** Those decisions are not approved yet.

| Field | Type | Meaning |
|---|---|---|
| `signal_name` | str | e.g. `long_pause_count` |
| `modality` | `audio` / `transcript` / `visual` / `recording` / `processing` | where the signal comes from |
| `value` | scalar or null | the measurement; `null` = not measurable (never guessed) |
| `confidence` | float in [0,1] or **null** | reserved; stays `null` until a scoring method is approved |
| `quality_status` | `ok` / `warning` / `unusable` / `unknown` | quality of the *modality* the signal came from |
| `supporting_timestamps` | list of (start, end) s | where to look in the recording |
| `supporting_transcript_span` | {text, start, end} or null | relevant transcript text |
| `explanation` | str | plain-language description of what was measured, not a verdict |
| `source_features` | list of feature names | features the signal was derived from |
| `sample_key` | str | `recording_id/question_id[/augmentation]` |

## Rules

1. **Quality is never evidence.** Features registered as `kind=quality` (noise, clipping,
   silence) can't appear in `source_features`; validation rejects them. Instead they set
   `quality_status` for that modality: silent audio makes audio signals `unusable`, noise
   makes them `warning`.
2. **Missing stays missing.** A signal without a measurable value has `value=null`,
   `quality_status=unknown` and says "not measurable".
3. **No verdicts.** Explanations describe measurements ("Pauses ≥ 1.0 s: 3"). They never
   say "cheating" or "AI-generated".
4. **Michigan is not AI-assistance evidence.** Signals computed on deception datasets
   describe delivery only. Their labels are `deception_label`, never assistance.

## Producing signals today

`describe_feature(sample, "long_pause_count")` wraps one registered behavioral feature as
a neutral signal: the answer window as timestamps, the transcript span for transcript
features, per-modality quality status, and `confidence=None`. Visual extractors
(teammates) emit `visual_*` features. Once registered, they can be described the same way.

Feature kinds and modalities live in
[features/registry.py](../src/interview_integrity/features/registry.py). A test fails
if the pipeline emits an unregistered feature.
