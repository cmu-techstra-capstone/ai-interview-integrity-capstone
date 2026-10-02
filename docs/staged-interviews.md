# Staged Interviews: Backend Support

Staged interviews are our only source of AI-assistance ground truth. The recording
protocol itself is still to be designed with the team and the IRB. This page covers what
the backend expects.

## Per-recording metadata (JSON)

Full example: [examples/staged_interview_metadata.json](../examples/staged_interview_metadata.json)

| Field | Level | Required | Notes |
|---|---|---|---|
| `interview_id`, `participant_id`, `source_dataset="staged"` | recording | yes | pseudonymous IDs only (e.g. `P010`) |
| `recording_id` | recording | no | defaults to `interview_id`; augmented variants share it |
| `question_id` | question | yes | unique within the recording |
| `assistance_label` | question | yes for staged | `HUMAN_UNASSISTED`, `AI_ASSISTED`, `AI_VERBATIM`, `AI_PERSONALIZED`. It's *how the answer was produced*, recorded at collection time |
| `question_text` | question | recommended | enables the QA overlap feature |
| `question_start`, `question_end` | question | recommended | seconds from recording start; `question_end` enables `response_latency` |
| `answer_start`, `answer_end` | question | required if > 1 question per video | otherwise the answer is searched for after `question_end` |
| `ai_model_used`, `ai_prompt_used`, `generated_ai_answer` | question | no | **never required for `HUMAN_UNASSISTED`**; the quality report warns if AI-labelled answers lack them |
| `response_notes` | question | no | free-text protocol notes |
| `deception_label` | question | no | normally `UNKNOWN` for staged data |

Rows keep `video_reference` (local path or remote URI), `video_sha256` and
`audio_reference` for traceability.

## Adding a recording

1. Upload the video, plus a transcript if one exists, to private shared storage under
   `datasets/staged_interviews/`, and the metadata JSON under `metadata/staged_interviews/`.
2. Add a row to `manifests/files/staged_interviews.csv` with `drive_location`,
   `transcript_location`, `metadata_location`, `participant_id` and
   `file_status=IN_DRIVE`. The manifest must not contain answer text.
3. Process it, then check quality:

   ```bash
   interview-integrity process-remote --dataset staged_interviews --root "<shared root>"
   interview-integrity quality --input data/processed/samples.jsonl
   ```

Each question becomes one row. Outputs are written to
`processed/*/staged_interviews/<video_id>__<question_id>.json` in shared storage.
Staged outputs contain participant transcripts and AI prompts, so **they must not be
committed to GitHub**. Only public-dataset outputs live in this repo's `processed/`.

## Protocol suggestions (backend-relevant)

- Record the candidate and interviewer on **separate audio tracks**, or at least log
  `question_end`. This avoids needing diarization.
- Use a within-subject design: each participant answers under several conditions. This
  makes within-participant normalization possible.
- Capture AI metadata during the session, not afterwards.
- Run `interview-integrity split` (grouped by participant) before any modelling.
