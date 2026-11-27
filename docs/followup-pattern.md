# Follow-up Pattern (timeline fusion, exploratory)

**Status:** research prototype on branch `model/video-behavior-research`. Not integrated
into product APIs. No AI-assistance ground truth exists, so this rule is **unvalidated**.

## What it does

For each interview answer it checks three measured conditions and reports which were met:

| Condition | Measured from | Default rule |
|---|---|---|
| `delayed_start` | ASR word timestamps aligned to the speaker-labelled transcript | answer starts >= 2.0 s after the question ends |
| `look_away` | `experiments/video/relative_events.py` timeline | a sustained (>= 2 s) head or gaze change of >= 15 deg from the candidate's own baseline overlaps [question end, answer start + 3 s] |
| `fluent_answer` | human transcript (fillers) + ASR timing (pauses >= 1 s) | filler rate and long-pause rate both <= the candidate's own median answer |

All three met → `suggest_followup`. Any not met → `no_pattern`. Otherwise
`insufficient_evidence` (the system abstains instead of guessing).

Optional context, never required: `read_like_delivery` (audio read-vs-spontaneous model)
and `ai_like_text` (Desklib). Both were trained on non-interview data.

`ai_assistance_probability` is always `null`. Output wording describes measurements only.

## Why these choices

- **Within-person fluency.** Comparing an answer with the same candidate's other answers
  avoids penalising accents, non-native speakers or a habitually careful style.
- **Fillers from the human transcript.** ASR often drops "uh/um", so filler counts use the
  transcript; ASR is used only for timing.
- **Abstain on weak alignment.** If the end of the question or the start of the answer was
  not matched to ASR words, latency and look-away are `unmeasurable`.
- **Calibration period excluded.** Look windows inside the first 30 s (the video baseline)
  are `unmeasurable`.

## LLM reviewer brief (`fusion/llm_brief.py`)

Only for `suggest_followup` answers. The LLM receives the computed conditions and the
interviewer's question (not the candidate's answer text unless explicitly approved) and
returns JSON: summary, observations with timestamps, alternative explanations, 1-3
follow-up questions, limitations. `validate_brief` rejects verdict words, probabilities or
percentages, and timestamps that are not in the input. No provider is wired yet
(`llm/openrouter.py` is still a placeholder).

## MIT run

`experiments/fusion/run_mit.py` (asr → evaluate → summarize). MIT interviews are ordinary,
unassisted interviews, so the suggest rate there is a **false-positive proxy**, not
accuracy. Aggregate results: `reports/fusion/`. Per-recording outputs stay in ignored
`data/processed/fusion/`.

## Known limitations

- No AI-assistance labels: the rule can only be checked for how often it fires on normal answers.
- MIT gaze/head events come from an oblique camera with a natural (not guided) baseline.
- Thresholds (2 s, 15 deg, 3 s) are hand-picked; see the sensitivity grid in the report.
- Looking away while thinking is normal and culturally variable; this is why the pattern
  only suggests a follow-up question.
