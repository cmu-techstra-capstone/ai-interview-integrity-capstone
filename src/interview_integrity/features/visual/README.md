# Visual features (shared team area, not started)

Future visual features plug into the pipeline through `features/base.py`
(`FeatureExtractor` + `AnswerContext`). No visual model has been chosen yet. Gaze,
facial-expression, pose, face and deepfake models all need **team approval** first.

Contract for an extractor placed in this package:

- `name`: a unique identifier. `prefix`: a namespace starting with `"visual_"`, e.g.
  `"visual_gaze_"`, so two extractors can't collide. Every returned key must start with
  it. Quality metadata (e.g. "face visible", "frame too dark") goes under a `"quality_"`
  prefix, so it's never treated as evidence.
- `extract(ctx)` reads `ctx.video_path`, restricted to `[ctx.answer_start, ctx.answer_end]`,
  and returns a flat `dict[str, float | int | str | None]`.
- Return scalars (`float | int | str | bool`) or `None`. Return `None` for values that
  can't be measured; never guess.
- Behavioral `visual_*` features can be wrapped as signals following
  [docs/evidence-contract.md](../../../../docs/evidence-contract.md).
- Don't write next to the source video, and don't keep frames. Any frame cache must be
  temporary.
- Add a test using the generated test videos in `tests/conftest.py`. Don't commit real
  recordings.

Register it per run:
`process_video(..., config=PipelineConfig(extractors=[YourExtractor()]))`.
