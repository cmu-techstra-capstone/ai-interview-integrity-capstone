# Video behavior research

Local component experiments for Techstra. Research date: 2026-10-29.

The pipeline measures head/gaze direction, missing-face detections and multiple faces,
and emits timestamped review events. Training labels are visual directions, not verified
AI assistance. Full investigation and measured results are in
[the research report](../../reports/video/video-research-20261029.md).

## Environment

From this worktree root, create a Python 3.12 environment and install:

```bash
uv venv --python 3.12 .venv-video
uv pip install --python .venv-video/bin/python -r experiments/video/requirements.txt
```

On this Mac, MediaPipe needs access to the macOS graphics service even with its CPU
delegate selected. The experiment ran outside the restrictive graphics sandbox. Inference
is local; no frames are submitted to an inference API.

Use `MPLCONFIGDIR=.cache/matplotlib` to keep the plotting cache local.

## Acquisition

Review each source's terms before use. Scenario data is CC BY 4.0; Columbia and
Gaze360-derived weights are for this noncommercial research experiment. Do not redistribute
the raw archives, images or weights through this repository.

The following local acquisition was executed:

```bash
mkdir -p data/raw/video_research data/models/video_research
curl -fsSL https://data.mendeley.com/public-api/datasets/mjrfmvsh7d -o data/raw/video_research/scenario_metadata.json
curl -fsSL https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task -o data/models/video_research/face_landmarker.task
curl -fsSL https://github.com/yakhyo/gaze-estimation/releases/download/weights/mobileone_s0_gaze.onnx -o data/models/video_research/mobileone_s0_gaze.onnx
.venv-video/bin/python experiments/video/download_scenarios.py --per-sequence 70
PYTHONPATH=src .venv-video/bin/python experiments/video/download_columbia.py
```

Scenario selection is fixed before inference: 70 evenly spaced filenames in each
of 11 source sequences. It verifies the author's per-file SHA-256 hashes. Columbia
selection covers all 56 people, all 21 gaze targets and the zero-degree head pose.
Its range reader verifies the original ZIP CRC and records local SHA-256 hashes.
The Columbia transfer is about 490 MB, saving a download of the entire 2.38 GB archive.

## Reproduce experiments

Prefix commands with `MPLCONFIGDIR=.cache/matplotlib LOKY_MAX_CPU_COUNT=4` if needed.

```bash
.venv-video/bin/python experiments/video/benchmark.py extract
.venv-video/bin/python experiments/video/benchmark.py train
.venv-video/bin/python experiments/video/benchmark.py extract --gaze-model data/models/video_research/mobileone_s0_gaze.onnx --features data/processed/video_research/frame_features_gaze.jsonl
.venv-video/bin/python experiments/video/compare_gaze.py
.venv-video/bin/python experiments/video/columbia_benchmark.py extract
.venv-video/bin/python experiments/video/columbia_benchmark.py train
.venv-video/bin/python experiments/video/threshold_experiment.py
```

The first dataset uses leave-one-person-out evaluation. Columbia uses five participant
folds. The threshold experiment selects the cutoff inside three additional training-only
participant folds in each outer fold. Parameters are fixed. Later comparisons are
exploratory iterations on the same cohort, not a preregistered final benchmark.

The low-false-positive gaze candidate uses class-balanced histogram gradient boosting
with depth 3, 150 iterations, learning rate 0.05 and L2=1. The nominal threshold-training
target is 10% FPR. Held-out aggregate results: AUROC 0.8414, FPR 7.74%, recall 60.12%,
balanced accuracy 76.19%. Target labels represent gaze direction, not AI use.

Exported `phase3/` bundles combine the CSD head classifier and Columbia gaze classifier.
The eye classifier is gated on a single visible face, measurable eyes, and a centered
head prediction. The final full-data threshold is an experimental deployment artifact;
the reported evaluation uses separate fold-specific thresholds, not that final threshold.

## Run a local video

```bash
.venv-video/bin/python experiments/video/video_pipeline.py /absolute/path/to/video.mp4 --gaze-model data/models/video_research/mobileone_s0_gaze.onnx --classifiers data/processed/video_research/phase3 --sample-fps 5 --min-event-seconds 2 --out data/processed/video_research/my_video
```

For an initial inspection, add `--max-seconds 60`. The output directory contains
`measurements.jsonl` and `timeline.json`, including quality counts, event start/end times,
source hash and local processing latency. `ai_assistance_probability` stays null.
Absence events mean **no face detected**, which may include occlusion or detector failure.
The 2-second duration is an engineering default, not a learned cheating threshold.

## MIT transfer checks

The supplied README describes 69 students, each recorded before and after career
counseling (P and PP). These are not assisted/unassisted conditions. Official ratings,
including EyeContact and Authentic, are not AI-use labels.

Place authorized archives under ignored `data/raw/video_research/mit/`. To audit the
official features and labels, then prepare and inventory the separate video archive:

```bash
.venv-video/bin/python experiments/video/mit_feature_audit.py
.venv-video/bin/python experiments/video/prepare_mit_video.py /absolute/path/to/Videos.zip
.venv-video/bin/python experiments/video/batch_transfer.py data/raw/video_research/mit/videos --probe-only
```

The feature audit checks ZIP CRC, missing values, recording/participant counts and
joins. The transcript CSV has no header. The original pose units are not documented
in the supplied README; these CSV columns cannot replace the MediaPipe/MobileGaze
features the classifiers were fitted on. Per-recording inventories remain local.

Once footage has been visually checked for candidate framing, first run paired
recordings P1/PP1, P2/PP2 and P3/PP3 as an engineering pilot, then expand coverage:

```bash
.venv-video/bin/python experiments/video/batch_transfer.py data/raw/video_research/mit/videos --include-stems P1 PP1 P2 PP2 P3 PP3 --max-seconds 60 --out data/processed/video_research/mit_pilot
.venv-video/bin/python experiments/video/batch_transfer.py data/raw/video_research/mit/videos --out data/processed/video_research/mit_full
```

This is a fixed convenience pilot, not a representative evaluation sample. Batch
outputs report measurable coverage separately from positive frame/event rates,
plus local elapsed time and errors. Cache reuse checks source, code, model and
configuration hashes. Observed event rates are **not** false-positive rates. MIT
AI-assistance AUROC remains null without ground-truth assistance labels. Event
accuracy also requires independent timestamp annotations. Research terms prohibit
redistribution and require destruction of original videos after the research ends.

## Verification and lightweight reports

```bash
.venv-video/bin/python -m pytest -q experiments/video/test_video_research.py
.venv-video/bin/python experiments/video/quality_smoke.py
.venv-video/bin/python experiments/video/audit_and_plot.py
```

`audit_and_plot.py` expects the two public example-video checks from the report to be
present under `final_demo_default/` and `final_demo_multiface/`. Source clips came from
the OpenFace authors' `samples/default.wmv` and `samples/multi_face.avi` in their GitHub
repository. They are engineering examples, not a labeled interview test set.

Only code, aggregate reports and a monochrome result figure are intended for Git.
All media, measurements and model binaries remain under ignored `data/` paths.

## Third-party attribution

- Google MediaPipe Face Landmarker: official version-1 float16 task bundle; 478 face
  landmarks and facial transformation matrix. See [Google's guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python).
- Yakhyokhuja Valikhujaev, MobileGaze: published MobileOne-S0 ONNX model trained on
  Gaze360; [MIT code repository](https://github.com/yakhyo/gaze-estimation).
  The local implementation follows the publisher's RGB/ImageNet normalization and
  90-bin angle decode. Face crops use MediaPipe rather than the publisher's RetinaFace,
  so this is not a reproduction of the publisher's headline angular-error benchmark.
- Sucianna Ghadati Rabiha: [Cheating Scenario Dataset in Online Exam](https://doi.org/10.17632/mjrfmvsh7d.1), CC BY 4.0.
- Brian A. Smith, Qi Yin, Steven K. Feiner and Shree K. Nayar: *Gaze Locking: Passive
  Eye Contact Detection for Human–Object Interaction*, UIST 2013; Columbia Gaze Dataset.
- Petr Kellnhofer, Adrià Recasens, Simon Stent, Wojciech Matusik and Antonio Torralba:
  *Gaze360: Physically Unconstrained Gaze Estimation in the Wild*, ICCV 2019.
