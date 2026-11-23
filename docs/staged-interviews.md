# Staged Interviews: Protocol and Backend Support

Staged interviews are our only source of **AI-assistance ground truth**. They use
consenting staged participants only, **never real candidates**. Items marked
**(team decision)** are open; this page lists options, not choices.

## 1. Identifiers

| ID | Convention | Example | Notes |
|---|---|---|---|
| `participant_id` | `P` + 3 digits | `P007` | pseudonymous; the mapping to real identity is kept separately, access-restricted, never in Git or metadata |
| `interview_id` | `STG-<participant>-S<session>` | `STG-P007-S01` | one recording session |
| `recording_id` | defaults to `interview_id` | `STG-P007-S01` | augmented variants keep it and set `augmentation` |
| `question_id` | `Q` + 2 digits, from a shared question bank | `Q03` | same ID = same question text across participants |

`interview-integrity staged validate` warns when IDs don't follow these patterns.
Question bank example: [config/question_bank.example.json](../config/question_bank.example.json).

## 2. Assistance conditions

| Label | Participant behavior |
|---|---|
| `HUMAN_UNASSISTED` | answers alone; no AI tool open |
| `AI_ASSISTED` | consults AI output, then answers in their own words and structure |
| `AI_VERBATIM` | reads the AI-generated answer aloud (near-)word-for-word |
| `AI_PERSONALIZED` | delivers the AI answer adapted with their own experience or details |

Verbatim vs personalized: if most sentences of the spoken answer can be matched to the
generated text, it's `AI_VERBATIM`. If the structure or content comes from the AI but
the participant substantially rewords it or adds their own specifics, it's
`AI_PERSONALIZED`. Record the *intended* condition. If behavior drifts (e.g. told to
personalize but reads verbatim), keep the label of what actually happened and explain
in `response_notes`.

**Condition assignment (team decision):** options include (a) a within-subject Latin
square, where every participant sees every condition and each question appears under
each condition across participants, or (b) a fixed condition order. (a) separates
speaking style from condition and is what the "within-participant normalization"
feature needs. (b) is simpler but confounds order and fatigue with the condition. Avoid
telling participants in advance which signals are measured.

## 3. Recording workflow

1. Consent (section 6), then a short practice question that isn't analyzed.
2. For each question: the interviewer reads the question, the participant answers under
   the assigned condition, and AI metadata is captured immediately (section 5).
3. Upload the recording straight to private shared storage. It never stays on a
   personal laptop or goes into Git.
4. Fill in metadata (`staged template`), import timestamps (`staged import-labels`),
   and run `staged validate`.

**Separate interviewer and candidate audio tracks (team decision):**

| Option | Pros | Cons |
|---|---|---|
| Separate tracks (e.g. each person on their own mic/channel, or meeting software that records per-participant audio) | Clean candidate-only audio; no diarization needed; reliable latency and pauses | Needs suitable recording setup; must keep tracks in sync |
| Single mixed track + logged timestamps | Simplest setup | Interviewer speech must be excluded via `question_end`/answer windows; timestamp effort per question |
| Single mixed track + automatic diarization | Least manual work | Needs a diarization model (not approved); errors propagate into features |

The backend supports all three: answer windows and `question_end` already restrict
analysis, and a diarizing STT can plug in later.

## 4. Timestamp capture

Needed per question: `question_start`, `question_end` (enables `response_latency`),
`answer_start`, `answer_end` (required when a recording has several questions).

Options: a label file made after recording in any audio tool that exports
`start<TAB>end<TAB>label`, such as Audacity label tracks, with labels like `Q01 question`
and `Q01 answer`. Or the interviewer logs key presses live and converts them to the same
format. Import with:

```bash
interview-integrity staged import-labels --metadata STG-P007-S01.metadata.json --labels STG-P007-S01.labels.txt
```

If `answer_start` is missing, the pipeline searches for speech after `question_end`.
It never invents latency.

## 5. AI metadata (AI_* conditions)

| Field | Capture |
|---|---|
| `ai_model_used` | exact model/version string shown by the tool |
| `ai_prompt_used` | the exact prompt typed or pasted by the participant |
| `generated_ai_answer` | the exact AI output on screen (copy-paste, not paraphrase) |
| `response_notes` | deviations, e.g. "skipped last paragraph", "added own project" |

These are optional for `HUMAN_UNASSISTED` answers. If an AI answer was generated only
for comparison, keep the label `HUMAN_UNASSISTED`. The validator warns so it's
deliberate.

## 6. Consent, privacy, retention

- **IRB:** follow CMU IRB guidance before any recording. Consent covers recording
  (video and voice), research use, who can access the data, retention period, and any
  third-party processing (e.g. a hosted STT, which isn't approved).
- **Minimize PII:** ask participants not to state their name, employer or other
  identifying details. Use pseudonymous IDs everywhere. Don't record more than needed
  (e.g. audio-only if video isn't required for a study).
- **Storage:** raw recordings live only in private shared storage with team-only access.
  Never in GitHub, never permanently on laptops. `.gitignore` blocks staged outputs
  under `processed/`.
- **Outputs:** staged feature rows contain transcripts and prompts. Treat them as
  personal data and keep them in private storage.
- **Retention:** define a deletion date at consent time (team decision). Delete raw
  media and derived transcripts when it passes or when a participant withdraws.
- **Withdrawal:** remove the participant's media, metadata and derived rows, then re-run
  splits.

## 7. Backend: from recording to dataset

Full metadata example: [examples/staged_interview_metadata.json](../examples/staged_interview_metadata.json).
All fields are validated by the schema. AI fields are optional, and timestamps are in
seconds from the recording start.

```bash
interview-integrity staged template --interview-id STG-P007-S01 --participant-id P007 \
  --question-bank config/question_bank.example.json \
  --condition Q01=HUMAN_UNASSISTED --condition Q02=AI_VERBATIM --out pilot/STG-P007-S01.metadata.json
interview-integrity staged import-labels --metadata pilot/STG-P007-S01.metadata.json --labels pilot/STG-P007-S01.labels.txt
interview-integrity staged validate pilot/*.metadata.json
interview-integrity process-batch --dir pilot --out-dir data/pilot_out     # one row per question
interview-integrity quality --input data/pilot_out/samples.jsonl
```

From shared storage instead of a local folder: add manifest rows to
`manifests/files/staged_interviews.csv` with `metadata_location`, then run
`interview-integrity process-remote --dataset staged_interviews --root <shared root>`.
