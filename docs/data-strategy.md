# Data Strategy

This document describes where our data comes from, how it is labeled, and the rules
that keep the dataset scientifically valid and ethically handled.

## 1. What we are (and are not) measuring

The system estimates signals of **possible real-time AI assistance** during a virtual
interview, to help a human interviewer decide whether follow-up questioning is
worthwhile. It never labels a candidate as cheating. All features are explainable
research signals, not proof.

## 2. Video-first representation

Every recording is kept as the original video. The pipeline derives:

```text
Video (preserved, never modified; SHA-256 recorded)
 ├── visual/video data   -> reserved for future work (not analyzed in the MVP)
 ├── audio.wav           -> 16 kHz mono PCM, used for timing features
 └── transcript.json     -> segments + word timestamps, used for linguistic features
```

One dataset row = one answer to one question in one recording (`InterviewSample`,
see `src/interview_integrity/datasets/schema.py`).

## 3. Dataset sources

### 3.1 Staged interviews: the eventual primary ground truth

Controlled mock interviews that the team records. Each answer is produced under a known
condition:

| `assistance_label`  | Meaning (how the answer was actually produced)                      |
|---------------------|---------------------------------------------------------------------|
| `HUMAN_UNASSISTED`  | Participant answered with no AI help                                |
| `AI_ASSISTED`       | Participant consulted AI output but answered in their own words     |
| `AI_VERBATIM`       | Participant read out AI-generated text (near-)verbatim              |
| `AI_PERSONALIZED`   | Participant delivered AI output adapted to their own experience     |
| `UNKNOWN`           | Condition not recorded                                              |

Protocol notes:
- The label describes the **production process**, recorded at collection time, not a
  judgement made afterwards from the video.
- Ideally the same participant answers comparable questions under several conditions
  (within-subject design), so that individual speaking style isn't confounded with the label.
- Record `question_end`, `answer_start` and `answer_end` timestamps at collection time
  whenever possible; otherwise response latency cannot be measured and stays `null`.
- AI assistance is **not** the same as deception: an `AI_PERSONALIZED` answer can be
  factually true, and an unassisted answer can be false.

### 3.2 Public multimodal deception datasets: supporting data only

| Dataset | Use for us |
|---|---|
| DOLOS | Multimodal pipeline development; audio/visual behavior research |
| Real-life Deception (University of Michigan, courtroom trials) | Same |
| Bag-of-Lies | Same |

These are useful for building and stress-testing the audio/transcript/video pipeline and
for studying behavioral signals in general. **They do not contain AI-assistance ground
truth.**

- Their truth/deception labels go in `deception_label` only.
- `assistance_label` for these sources must be `UNKNOWN`. The schema enforces this and
  rejects any other value for `dolos`, `real_life_deception` and `bag_of_lies`.
- Each dataset has its own license and access agreement. Obtain access individually,
  follow its terms (typically research-only, no redistribution), and **never commit
  these files to the repository**.
- Placeholders: put local copies under `data/raw/<dataset_name>/` (gitignored) and write
  a small adapter that emits one metadata JSON per clip (see
  `examples/public_dataset_metadata.json`).

## 4. Labels are independent axes

```text
assistance_label  ∈ {HUMAN_UNASSISTED, AI_ASSISTED, AI_VERBATIM, AI_PERSONALIZED, UNKNOWN}
deception_label   ∈ {TRUTHFUL, DECEPTIVE, UNKNOWN}
```

Never map one onto the other (for example "DECEPTIVE ⇒ AI_ASSISTED"). Models trained to
predict assistance must only be trained and evaluated on rows with a known assistance label.

## 5. Augmentation and leakage

We may later add realistic video-call degradations to staged recordings: compression,
lower resolution, lighting changes, microphone/background noise, mild cropping, and
network-quality artifacts. We are not doing generative (frame-by-frame) video synthesis.

Rules:
1. An augmented variant keeps the original's `interview_id`, `participant_id` and
   `recording_id`, and sets `augmentation` to a short name (e.g. `compress_crf35`).
   Rows are unique by `(recording_id, question_id, augmentation)`.
2. **All variants of a recording, and all recordings of a participant, must stay in the
   same train/val/test partition.** `interview-integrity split` groups by
   `participant_id` by default and refuses to write if it detects cross-split leakage
   (`find_group_leakage`).
3. Assign splits by participant before augmenting, or re-run `split` afterwards. Never
   split at the row level.
4. Evaluation should report results on clean originals as well as augmented test variants.
5. Start small: a handful of well-defined transforms, not hundreds of generated videos.

## 6. Handling raw candidate data

Interview recordings are personal data (face, voice, and possibly biographical details).

- **Consent:** staged participants must give informed consent covering recording, the
  research purpose, and retention. Follow CMU IRB guidance before collecting data.
- **Never commit media or transcripts.** `data/raw`, `data/interim` and `data/processed`
  are gitignored, and so are common media extensions. Share data through the team's
  approved storage, not GitHub.
- **Pseudonymous IDs:** use IDs like `P001` rather than names in metadata and filenames.
  Keep any ID-to-identity mapping separate and access-restricted.
- **Minimize:** don't collect more than the study needs. Delete derived artifacts when
  they are no longer needed.
- **No automated decisions:** outputs are research signals. The system must not be used
  to reject candidates automatically.
- **Third-party APIs:** sending audio or transcripts to a hosted STT/LLM provider is a
  data transfer. Confirm this is allowed under the consent terms first (see
  `docs/decisions.md`).
