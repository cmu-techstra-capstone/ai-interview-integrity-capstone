# Interview Signal Agent — live demo (backend walkthrough)

A local stand-in for the "hop-on meeting agent". Transcript turns arrive one by one (or as you type),
a **0–9 signal score** updates live (**0–3 low · 4–5 review · 6–9 high/red**), the tool explains *why*,
and it suggests **follow-up questions** for the human interviewer. Audio can be analyzed for
pause/cadence timing and blended into the score.

**Zero installs:** Python 3.10+ standard library only. (ffmpeg is optional, for non-WAV audio.)

## Run it

```bash
git fetch origin demo/live-signal-agent
git checkout demo/live-signal-agent
python demo/smoke_test.py      # optional: 2-second check, should print all PASS
python demo/server.py          # then open http://127.0.0.1:8765
```

This branch is based on the tip of PR #6 (which contains PRs #1–#6), because the demo imports the repo's
`interview_integrity` linguistic, VAD and timing code from `src/`. It changes no existing file.

## Demo script (about 4 minutes)

1. Pick **"Mixed: natural at first, then AI-style answers"** → **Load** → **Auto-play**.
   Watch the gauge sit green on the first two answers, then climb into amber and red when polished,
   generic answers start. Point at **Why this score** (filler words, transitions, buzzwords, concrete detail).
2. Show **Suggested follow-up questions** under each answer.
3. Click **Reset**, load **Unassisted** → stays green. Then **AI-style** → red throughout.
4. **Type live:** paste any answer into the "type live" box and watch the gauge preview as you type.
5. **Audio:** upload a recording (WAV, or mp3/m4a/mp4 if ffmpeg is installed) → timing score,
   speech/pause timeline, then **Combine with latest transcript answer**.
6. **Reality check:** click *Score the repo's 121 real human clips* → 115 low, 6 review, **0 high**.

## Follow-up questions via prompting

Set one of these *before* starting the server for LLM-written follow-ups (otherwise it uses offline templates,
and the UI says which one it used):

```bash
export ANTHROPIC_API_KEY=...        # or OPENROUTER_API_KEY=...
export DEMO_LLM_MODEL=...           # optional model override
python demo/server.py
```

The prompt (see `followups.py`) tells the model to write depth probes about specifics, ownership,
trade-offs and failure, and never to accuse the candidate.

## Be upfront about these limits

- The score is a **hand-weighted heuristic over the repo's linguistic/timing features**, not a trained or validated
  detector. It has **no measured accuracy**; the samples are hand-written and exaggerated.
- The only real-data check is **false positives on real human speech** (courtroom clips from the Michigan deception
  dataset: short, not interviews, not AI-assisted). There are no AI-assisted positives in the repo's data.
- Speech-to-text often drops "um/uh", which makes natural speech look more polished.
- Audio thresholds are **uncalibrated** and were only exercised on synthetic audio. Timing is weak evidence by design.
- Scores are decision support for a human interviewer, never proof of misconduct.

## Files

| File | Purpose |
|---|---|
| `server.py` | stdlib HTTP server + JSON API |
| `index.html` | single-page UI (gauge, timeline, feed, audio) |
| `scoring.py` | explainable 0–9 scoring, transcript parsing, running score |
| `audio.py` | VAD + timing analysis (repo code), optional Whisper if installed |
| `followups.py` | LLM prompt + offline fallback |
| `samples.py` | hand-written sample interviews |
| `smoke_test.py` | quick self-check |
