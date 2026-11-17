# Demo handoff: video + GPT follow-up layer

For whoever builds the demo on top of PR #10 (`feature/end-to-end-integration-v1`). Branch:
`model/video-behavior-research`. Everything here is research code; nothing in it decides that a
candidate used AI.

## What this branch adds

| Layer | Code | What it does |
|---|---|---|
| Video signals | `experiments/video/` | MediaPipe head pose + frozen MobileOne-S0 gaze (Gaze360), baseline-relative events: sustained (>= 2 s) change >= 15 deg from the candidate's own first-30 s baseline. Report: `reports/video/` |
| Timeline fusion | `src/interview_integrity/fusion/followup.py` | Per answer: `delayed_start` (>= 2 s), `look_away` (event overlapping question end -> answer start + 3 s), `fluent_answer` (fillers and long pauses <= own median). All three -> `suggest_followup`; any unmeasurable -> `insufficient_evidence`. Doc: `docs/followup-pattern.md` |
| GPT reviewer brief | `src/interview_integrity/fusion/llm_brief.py`, `llm/openrouter.py` | Only for `suggest_followup` answers. LLM gets the computed conditions + interviewer question (not the answer text) and returns summary, alternative explanations, 1-3 follow-up questions. `validate_brief` rejects verdicts, probabilities, percentages and invented timestamps. |
| Demo export | `src/interview_integrity/fusion/demo_export.py` | Per-answer fragment with `analysis.v1`-shaped `evidence_signals` + a `followup_pattern` block (status, conditions, accepted brief or null). |
| Synthetic positives (research, not needed for demo) | `src/interview_integrity/synthetic/`, `docs/synthetic-positives.md` | AI-written answers to MIT questions vs real answers; content rubric. Result: content alone only catches verbatim copying. |

## One command: analyze one recorded interview (post-interview)

`experiments/fusion/analyze_video.py` takes a video and a speaker-labelled transcript and writes one
JSON for the dashboard. Run from the worktree root with `.venv-video` (MediaPipe, OpenCV, sklearn,
onnxruntime). Model files are local: `data/models/video_research/` and
`data/processed/video_research/phase3/` (see `experiments/video/README.md`).

```bash
# MIT demo: reuses cached measurements and ASR words, about 1 s
.venv-video/bin/python experiments/fusion/analyze_video.py data/raw/video_research/mit/videos/P1.avi \
    --transcript mit:P1 --brief --include-text --out data/processed/analyze/P1.json

# New recording: transcript JSON with speaker names (times optional)
.venv-video/bin/python experiments/fusion/analyze_video.py interview.mp4 \
    --transcript interview.json --interviewer-name "Aditi Adgaonkar" --brief
```

- Transcript formats: MIT-style text, a JSON list of `{speaker, text, start?, end?, words?}`, or
  `analysis.v1` `transcript_segments`. Names other than interviewer/candidate need `--interviewer-name`.
- If the candidate's turns have no word timestamps, faster-whisper words are aligned to the transcript
  (`uv pip install --python .venv-video/bin/python faster-whisper`; model path `--asr-model`).
- `--brief` adds GPT reviewer briefs for flagged answers (needs `OPENROUTER_API_KEY` in `.env`).
- Speed check (3-minute MIT video, 4 CPU cores, nothing cached): 27 s in total.
- Verified: P1 gives the same answer windows, events and statuses as the batch MIT run.

### JSON fields for the dashboard

| Field | Show as |
|---|---|
| `status_counts` | header: how many answers suggest a follow-up |
| `visual.events[]` (`type`, `start_s`, `end_s`) | look-away timeline across the whole video; click to seek |
| `answers[].question_id`, `question_text` (with `--include-text`), `answer_start`, `answer_end` | one row per answer |
| `answers[].followup_pattern.status` | `suggest_followup` / `no_pattern` / `insufficient_evidence` badge, never a score |
| `answers[].followup_pattern.conditions[]` (`name`, `status`, `explanation`, `timestamps`) | checklist with seek links |
| `answers[].followup_pattern.reviewer_brief` (`summary`, `alternative_explanations`, `suggested_followup_questions`) | GPT panel; `null` unless accepted by the guardrails |
| `answers[].evidence_signals` | same shape as `analysis.v1` evidence signals |
| `disclaimer`, `ai_assistance_probability` (always `null`) | footer text |

The first 30 s are the visual baseline, so answers starting inside it are `insufficient_evidence`.
For real interviews, start with ~30 s of normal conversation before the first question.

## Replay all MIT results

Raw MIT media, transcripts, ASR words and per-recording results are **not in git** (dataset terms;
`data/` is ignored). They live on Leo's Mac under `techstra-video-research/data/processed/`. Run
there (or share the output folder privately, never via git):

```bash
# already done on Leo's Mac: run_mit.py asr / evaluate (138 recordings, 909 answers)
cp .env.example .env   # set OPENROUTER_API_KEY (OpenRouter account; never commit .env)
.venv-video/bin/python experiments/fusion/brief_mit.py --model openai/gpt-4o-mini --include-question-text
```

This writes `data/processed/fusion/demo/<recording>.json` for the 15 recordings with at least one
flagged answer (18 answers in total). Each file is a list of per-answer fragments:

```json
{"question_id": "q04", "answer_start": 111.23, "evidence_signals": [...],
 "followup_pattern": {"status": "suggest_followup", "ai_assistance_probability": null,
   "conditions": [{"name": "delayed_start", "status": "met", "value": 4.29, "timestamps": [[106.94, 111.23]]}, ...],
   "reviewer_brief_status": "accepted",
   "reviewer_brief": {"summary": "...", "alternative_explanations": [...], "suggested_followup_questions": [...]}}}
```

Sensible demo recordings: P1 (q04), P10 (q04, q06), PP1 (q03). Raw video: `data/raw/video_research/mit/videos/`.

## Plugging into PR #10

- `answers[i].evidence_signals` in `analysis.v1` has the same shape; append `fragment["evidence_signals"]`.
- Add `fragment["followup_pattern"]` to each answer (new field; bump the contract or keep it optional).
- Overlay: `FollowUpQuestions.tsx` can show `reviewer_brief.suggested_followup_questions`; show the
  conditions with their timestamps so a reviewer can jump to them. Keep `detection` as
  `model_unavailable`; do not present the follow-up status as a score.

## Running on a new (non-MIT) recording

`evaluate_interview(recording_id, windows, VisualTrack.from_timeline(timeline, measurements))` needs:

1. **Answer windows** (`fusion.turns.AnswerWindow`): question text, `question_end`, `answer_start`,
   `answer_end`, answer text and ASR words. MIT has no speaker timing, so `run_mit.py` aligns ASR
   words to the speaker-labelled transcript. For Meet/Zoom, use `analysis.v1` `transcript_segments`
   (speaker + word times) or separate interviewer/candidate tracks and build windows directly.
2. **Visual timeline**: `experiments/video/video_pipeline.py` then `relative_events.py` (model
   downloads and commands in `experiments/video/README.md`; weights stay in ignored
   `data/models/`). The first 30 s are the baseline, so start with ~30 s of the candidate looking
   at the screen normally; answers inside that period return `insufficient_evidence`.
3. **At least 3 measurable answers** for the personal fluency baseline.

## Honest numbers to show

- On 138 ordinary MIT interviews (no AI use) the rule flags 18 of 324 fully measurable answers
  (5.6%), mostly on hard behavioural questions. Treat every flag as "ask a follow-up", not evidence.
  Report: `reports/fusion/mit-followup-pattern-20261105.md`.
- No real AI-assisted recordings exist yet; the rule is unvalidated. Synthetic-text pilot:
  `reports/synthetic/mit-synthetic-content-20261105.md`.

## Tests

`PYTHONPATH=src pytest -q tests/test_fusion_*.py tests/test_llm.py tests/test_synthetic.py`
(no network, fake LLM clients). The full suite passes.
