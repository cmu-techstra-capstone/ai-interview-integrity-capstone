# Follow-up pattern on MIT interviews (2026-11-05)

Exploratory. MIT interviews are ordinary mock interviews with **no AI-assistance labels**,
so every `suggest_followup` here is an ordinary answer the rule would have flagged. The
rate is a false-positive proxy, not accuracy. `ai_assistance_probability` stays null.

Rule and code: [docs/followup-pattern.md](../../docs/followup-pattern.md),
`experiments/fusion/run_mit.py`. Raw numbers: `mit-followup-pattern-20261105.json`.

## Data and execution

- 138 recordings, 69 participants. ASR: local faster-whisper `base.en` (int8, greedy, VAD
  filter), about 30x real time on 4 CPU cores. No audio left the machine.
- ASR words aligned to the speaker-labelled MIT (Turker) transcripts → 909 answer windows.
- Visual input: the existing 2 fps relative head/gaze timelines (`mit_full_relative`, 2026-10-29).

## Results (default: latency >= 2 s, look window = answer start + 3 s)

| | Count |
|---|---|
| Answer windows | 909 |
| Reliable question-end / answer-start timing | 569 (63%) |
| All three conditions measurable | 324 |
| `suggest_followup` | **18** (5.6% of the 324; 15 of 138 recordings, max 2 per recording) |
| `insufficient_evidence` | 347 |

Response latency over reliable windows: median 0.98 s, p10 0.32 s, p90 2.46 s; 16.7% >= 2 s.

Condition rates among answers where all three were measurable: delayed start 23.8%,
look-away 42.3%, fluent 42.6%. Product if independent: 4.3%; observed 5.6%.

Sensitivity (suggest / answers decided):

| min latency | look +2 s | look +3 s | look +5 s |
|---|---|---|---|
| 1.0 s | 33 | 35 | 37 |
| 1.5 s | 25 | 27 | 29 |
| 2.0 s | 18 | 18 | 20 |
| 3.0 s | 12 | 12 | 13 |

## Findings

1. **About 1 in 18 normal, measurable answers matches the pattern.** In a 7-question
   interview that would suggest a follow-up for roughly 1 in 3 honest candidates.
   Usable only as a prompt for a follow-up question, never as evidence.
2. **Flags cluster on hard behavioural questions.** Nearly all 18 follow "tell me about a
   challenge", "your weaknesses", "change one thing about yourself" or "why hire you".
   People pause and look away to think on exactly these. MIT questions are standardised, so
   the next version should compare latency with *other candidates on the same question*.
3. **Look-away adds little on MIT.** It is met for 42% of answers and is only weakly related
   to delay (49% when delayed vs 40% when not). This matches the 10-29 report: natural
   baselines on an oblique camera are noisy. Guided calibration is still needed.
4. **Timing coverage is the main bottleneck.** 37% of windows lack reliable question-end or
   answer-start alignment (mostly the last words of the question not matched), and the first
   1-2 questions fall inside the 30 s visual baseline period.

## Spot checks

Raw ASR words around three flagged answers confirm the latencies are real silences (e.g. no
words between 106.7 s and 111.2 s in one recording). One case is a single word followed by a
~10 s silence, counted as a delayed substantive start.

## Next

- Normalise latency per question across candidates (needs a question-type map).
- Try `small.en` or relaxed edge matching to raise timing coverage.
- Guided calibration and a small team-recorded pilot with real AI use, to see whether the
  pattern fires more often than this 5.6% baseline.
