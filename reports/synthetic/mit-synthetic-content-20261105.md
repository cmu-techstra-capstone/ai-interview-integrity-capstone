# Synthetic AI answers vs real MIT answers: pilot (2026-11-05/06)

Exploratory pilot: 8 randomly chosen participants (seed 20261105), 76 real answers, 683 scored
synthetic answers (684 generated; 228 per generator). Generators: `openai/gpt-4o-mini`,
`anthropic/claude-haiku-5.5`, `meta-llama/llama-3.3-70b-instruct`. Blind judge:
`google/gemini-2.5-flash`. Total cost: $0.77. Raw numbers: `mit-synthetic-content-20261106.json`
(supersedes the 20261105 JSON, which was missing 71 Claude answers). Method:
`docs/synthetic-positives.md`.

AUROC = P(synthetic scores higher than real), 95% participant-bootstrap interval.
Values far below 0.5 also separate well, but in the other direction.

| | specificity | genericness | spoken_style | composite (fixed a priori) |
|---|---|---|---|---|
| AI_VERBATIM | 0.39 [0.32, 0.47] | **0.74** [0.69, 0.79] | **0.02** [0.01, 0.03] | **0.69** [0.62, 0.75] |
| AI_PERSONALIZED | 0.66 [0.60, 0.72] | 0.48 [0.42, 0.54] | **0.05** [0.02, 0.08] | 0.41 [0.35, 0.48] |
| AI_SPOKEN | 0.63 [0.58, 0.67] | 0.44 [0.40, 0.48] | **0.27** [0.20, 0.35] | 0.40 [0.36, 0.45] |

By generator (composite): Claude 0.32 [0.27, 0.37], GPT-4o-mini 0.56 [0.51, 0.62],
Llama 0.61 [0.56, 0.66]. Mean spoken_style: real 4.50, AI_VERBATIM 2.22,
AI_PERSONALIZED 2.52, AI_SPOKEN 4.02. Length: synthetic about 12% shorter
(n_words AUROC 0.44 [0.42, 0.45]).

## Findings

1. **The "generic and vague" hypothesis only catches lazy copying.** The pre-registered
   composite separates `AI_VERBATIM` (0.69) and reverses once the candidate gives the chatbot
   their background (0.41, 0.40): personalised AI answers look *less* generic and *more*
   specific than the real students' answers (specificity 2.99 vs 2.47).
2. **How it is said separates better than what is said.** `spoken_style` separates real from
   every condition, including the one asked to sound spontaneous (inverted AUROC 0.73).
   Caveat: real answers are verbatim transcripts of unplanned speech; synthetic answers are
   clean text. A candidate *reading AI text aloud* produces a transcript with some speech
   noise, so this gap is likely overstated. It targets the same behaviour as the audio
   read-vs-spontaneous model: a candidate second channel, not evidence.
3. **Results depend on which chatbot is used.** Claude's answers score as less generic than
   the real students' (composite 0.32); Llama and GPT-4o-mini more generic. A content signal
   tuned on one model may not transfer.
4. **Judge quality is acceptable.** 96-97% of evidence quotes were found verbatim in the
   answer; 1 of 760 responses was unparseable.
5. **Run note.** Claude Haiku 5.5 is a reasoning model; with a 600-token cap it sometimes
   spent the whole budget thinking and returned no text. Empty outputs now retry once at
   4,000 tokens; all 228 Claude answers are valid in the final run.

## Next

- Scale to all 69 participants (`--participants 69 --max-calls 15000`; about 8.6x the pilot cost).
- Read-aloud test: team members read a few AI answers aloud on camera and answer a few
  themselves. This checks whether `spoken_style` survives real speech + ASR, and gives the
  first real audio/video positives for the audio model and look-away (reading off a screen).
