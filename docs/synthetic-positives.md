# Synthetic AI-assisted answers (text/content channel)

**Status:** research prototype, branch `model/video-behavior-research`. Code:
`src/interview_integrity/synthetic/`, `experiments/synthetic/run_mit_synthetic.py`.

## Why

There are no real AI-assisted interviews, so no detector or rule can be checked against
positives. This builds a **partial** substitute for the content channel only: AI-written
answers to the same standardised MIT questions, next to the real students' answers.

It cannot simulate gaze, response latency, prosody or reading behaviour, so it does not
replace the staged recordings. Synthetic rows carry `synthetic_condition`; they are never
written into `assistance_label`.

## Generation (use 3)

For every eligible real answer (one of the 7 standard question types, >= 40 words), each
generator writes one answer per condition, matched to the real answer's length:

| Condition | What the "candidate" types into a chatbot |
|---|---|
| `AI_VERBATIM` | the question only; answer read out as written |
| `AI_PERSONALIZED` | own background first (their self-introduction from the other interview, never the target answer) |
| `AI_SPOKEN` | personalised, and asks to sound unplanned and conversational (hardest case) |

Default generators via OpenRouter, from three model families so results do not just
measure one model's style: `openai/gpt-4o-mini`, `anthropic/claude-haiku-5.5`,
`meta-llama/llama-3.3-70b-instruct`.

## Content rubric (use 2)

A judge from a different model family (`google/gemini-2.5-flash` by default; the run
refuses a judge that is also a generator) scores each answer **blind**. It is never asked
whether the text is AI-written; it scores four observable properties from 1 to 5 with
quoted evidence: `specificity`, `genericness`, `on_topic`, `spoken_style`.

Real and synthetic text are first normalised to the same transcript format (lowercase, no
punctuation, no fillers), so formatting cannot give the source away. Evidence quotes are
checked against the answer (hallucination check). `composite = mean(genericness,
6 - specificity)` was fixed before any results.

## Evaluation

AUROC of each score for synthetic vs real (`P(synthetic scores higher)`), overall, by
condition and by generator, with 95% intervals from a participant-grouped bootstrap.
`n_words` AUROC should stay near 0.5 (length matched). Reports are aggregate only.

How to read it: if the rubric separates real from `AI_VERBATIM` but not from `AI_SPOKEN`,
it only catches lazy copying. And even a good AUROC here only shows the rubric separates
*these generators' text* from *these students' answers*. It still needs the staged
recordings before it can count as evidence.

## Running (on the Mac; the cloud and the VM sandbox cannot reach OpenRouter)

```bash
cd "techstra-video-research"
cp .env.example .env    # then put OPENROUTER_API_KEY=... in .env (never committed)
.venv-video/bin/python experiments/synthetic/run_mit_synthetic.py extract
.venv-video/bin/python experiments/synthetic/run_mit_synthetic.py models
.venv-video/bin/python experiments/synthetic/run_mit_synthetic.py generate --participants 8
.venv-video/bin/python experiments/synthetic/run_mit_synthetic.py score --participants 8
.venv-video/bin/python experiments/synthetic/run_mit_synthetic.py evaluate
```

Every call is cached in ignored `data/processed/synthetic/llm_cache.jsonl`; rerunning or
raising `--participants` pays only for new items. `--max-calls` caps paid calls per run.

## Data handling

MIT answer text is sent to OpenRouter and the chosen providers (approved by the team on
2026-11-05). Generated text, scores and the cache stay in ignored `data/processed/synthetic/`.
