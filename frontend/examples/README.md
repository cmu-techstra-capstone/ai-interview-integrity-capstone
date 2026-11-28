# Importing a post-interview video analysis

The review app can show the output of `experiments/fusion/analyze_video.py`
(schema `followup_pattern.v1`, research branch / PR #12).

1. Generate the analysis for a recording, for example:
   `.venv-video/bin/python experiments/fusion/analyze_video.py interview.mp4 --transcript t.json --brief --include-text --out analysis.json`
2. In the app, open **Interviews** and click **Import video analysis**, then choose `analysis.json`.
3. The recording opens as a new interview. Use **Attach local recording** to play the video;
   timestamps in the Video tab and the follow-up check jump to the right moment.

What is shown:

- **Follow-up check** (replaces the 0-9 score for imported interviews): the follow-up status and
  the three required conditions (delayed start, look-away, fluent answer) with timestamps.
- **Video tab**: look-away events across the whole recording and near the selected answer,
  measured against the candidate's own first-30-second baseline.
- **Reviewer brief**: only when the LLM brief passed the guardrails; suggested questions can be
  added to the reviewer's notes.

Imported analyses never contain a score or probability; files that do are rejected.

`video-analysis.sample.json` is a synthetic example built from test fixtures (no real interview
data), so the import can be tried without any dataset. `npm test` checks the importer against it.
