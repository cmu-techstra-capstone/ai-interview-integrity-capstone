# Midterm Demo: Interview Signal Score

A small, runnable demo of the project's core idea: **watch an interview answer by answer, show a
live 0–9 "signal score" for possible AI assistance, and explain why.** It also suggests follow-up
questions the interviewer can ask. It supports a human reviewer; it never decides anything.

> **Honest status:** this is a *demo*, not the finished product. The score is a hand-weighted heuristic,
> not a trained or validated detector, and it has no measured accuracy yet. See [Limits](#limits-say-these-out-loud).

## Run it (about 60 seconds)

You need **Python 3.10 or newer**. Nothing to install.

```bash
git fetch origin demo/midterm
git checkout demo/midterm
python demo/smoke_test.py     # optional self-check, should print only PASS lines
python demo/server.py         # then open http://127.0.0.1:8765 in your browser
```

- Port busy? Use `python demo/server.py --port 8800`.
- The server runs on your own machine only. There is no hosted version.

## What you will see

| On the page | What it means |
|---|---|
| **Gauge (0–9)** | Running score for the interview so far. **0–3 low** (green), **4–5 review** (amber), **6–9 high** (red). |
| **Timeline** | One dot per candidate answer ("Answer 1", "Answer 2", ...). Vertical axis is the 0–9 score. |
| **Why this score** | The signals behind it, in plain words (for example "few filler words", "formal transitions"). |
| **Suggested follow-up questions** | Three probing questions per answer. Never accusations. |
| **Audio box** | Upload a recording to get a timing score and a speech/pause timeline. |

## 4-minute walkthrough for the midterm

1. Choose **Mixed** → **Load** → **Auto-play**. The first answers stay green (natural speech), then the
   score climbs through amber into red as polished, generic answers appear. Final scores: 0.1 → 0.6 → 4.3 → 5.1 → 6.0.
2. Point at **Why this score** and the **follow-up questions** under the answer.
3. **Reset**, load **Unassisted**: it stays green (ends at 0.8). Then **AI-style**: red throughout (ends at 7.9).
4. Type or paste any answer into the **type live** box and watch the gauge move as you type.
5. **Audio:** upload a recording (WAV works everywhere; mp3/m4a/mp4 need `ffmpeg`), then click
   **Combine with latest transcript answer** to blend timing into the score.

## How the score works

Each answer is checked for six signals. Each signal is 0–1; the weighted average becomes the 0–9 score.

| Signal | Looks "AI-like" when... | Weight |
|---|---|---|
| Spontaneity | very few "um/uh", repeats, self-corrections or hedges | 0.28 |
| Polish | formal transitions ("furthermore", "in conclusion") and list-like structure | 0.22 |
| Buzzwords | words like "leverage", "robust", "comprehensive" | 0.15 |
| Generic | no personal or concrete detail (names, numbers, "my last team") | 0.14 |
| Rhythm | sentences are unusually even in length | 0.13 |
| Completeness | long answer that echoes the question's terms | 0.08 |

**Audio timing** adds four weak signals (even speaking bursts, few pauses, very fast fluent delivery, long
silence before a fluent answer). When combined, the score is **70% transcript + 30% timing**.

**Short answers are pulled toward a neutral score**, because there is too little text to judge.
The interview-level score is a recency-weighted average, so recent answers count a bit more.

The signals come from the repo's own feature code (`src/interview_integrity/features/`); the weights and
thresholds live in `demo/scoring.py` and are **uncalibrated**.

## Follow-up questions

By default they come from offline templates, and the page says so. For LLM-written questions, set a key
**before** starting the server:

```bash
export ANTHROPIC_API_KEY=...      # or OPENROUTER_API_KEY=...
export DEMO_LLM_MODEL=...         # optional model override
python demo/server.py
```

The prompt (in `followups.py`) asks for depth probes about specifics, ownership, trade-offs and failure,
and forbids accusing the candidate. The live LLM path has not been tested end to end, so try it once before presenting.

## Limits (say these out loud)

- **Not validated.** No accuracy number exists. The three sample interviews are hand-written and exaggerated
  (`samples.py`); they are fixed text, not fetched or generated.
- **Only a false-positive check on real data:** 0 of the 121 real human clips (Michigan courtroom dataset)
  reach the red zone (`python demo/smoke_test.py`). Those clips are short, not interviews, and not AI-assisted.
  The repo has **no AI-assisted positive examples yet**, so detection rate is unmeasured.
- Speech-to-text often drops "um/uh", which makes natural speech look more polished than it was.
- Audio thresholds were only exercised on synthetic audio. Timing is weak evidence on its own.
- Scores are **decision support for a human interviewer, never proof of misconduct.**

## Where this fits in the project

- The demo **uses** the repo's existing pipeline code but is **not wired into it**. It changes no existing
  source file, and the repo's evidence contract still reports no confidence value.
- **Next step:** move this scoring into the main pipeline as a proper composite score (per-question and
  interview-level, calibrated low/review/high bands, tests), once labeled AI-assisted data exists to calibrate against.
- Job-requirement matching is intentionally **not** part of this demo.
- This branch is based on PR #6 (`7a2ea76`), which contains PRs #1–#6, because the demo imports that code.

## Files

| File | Purpose |
|---|---|
| `server.py` | Local web server and JSON API (standard library only) |
| `index.html` | The single-page UI: gauge, timeline, answer feed, audio box |
| `scoring.py` | Signal scoring, transcript parsing, running score, text + timing blend |
| `audio.py` | Voice-activity and timing analysis (uses repo code); optional Whisper if installed |
| `followups.py` | Follow-up question prompt, with offline fallback |
| `samples.py` | The three hand-written sample interviews |
| `smoke_test.py` | 2-second self-check, including the 121-clip false-positive check |
