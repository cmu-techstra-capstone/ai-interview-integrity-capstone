# MIT video transfer and calibrated gaze results — 2026-10-29

The complete MIT archive was processed locally. The main finding is that camera-relative direction rules do not transfer directly to oblique interview footage. Personal calibration is useful for direction scoring; it does not establish AI-assistance detection.

## Data and execution

- MIT: 138 videos from 69 people; 13.32 analyzed hours; 640 × 480, 29 fps source.
- Archive: 7,510,773,677 bytes; CRC passed for all AVI members; SHA-256 `744bd1392cb74b9f3deb1b8b3888dab3fb52492f5aa884bc8eeb39a8ad3fc42e`.
- Full run: 2 sampled frames/second, two workers, 95,945 measurements, zero processing errors.
- Fixed engineering pilot: first 60 seconds of six pre/post counseling recordings, 5 fps. All 1,695 measurable head frames triggered the absolute model; gaze coverage was zero.
- Full processing uses the original frozen MobileOne-S0 measurements. No MIT ratings were converted into AI-use labels, and no AI-use classifier was trained on MIT.

## MIT transfer results

The exploratory relative method uses only the first 30 seconds to estimate a rotation medoid and a typical gaze vector. Those seconds are excluded from evaluation. At least 10 valid calibration samples are required. Estimated direction changes must exceed 15° for at least 2 seconds. This is an unlabeled natural baseline, not a directed screen calibration.

| Measure | Result |
|---|---|
| Evaluation after calibration | 12.17 hours; 87,665 sampled frames |
| Head/gaze baseline available | 138/138; 123/138 recordings |
| Head measurable coverage, absolute → relative | 97.61% → 97.61% |
| Relative head positive frames / measurable frames | 16,945/85,574 (19.80%) |
| Gaze measurable coverage, absolute → relative | 2.34% → 54.05% |
| Relative gaze positive frames / measurable frames | 17,064/47,385 (36.01%) |
| Observed sustained events | `{"multiple_faces": 5, "no_face_detected": 51, "relative_gaze_change": 797, "relative_head_change": 769}` |
| Batch approximate wall time | 50.2 minutes; excludes download/probing |
| Sample inference median / P95 | 54.2 / 77.7 ms with two workers |

Coverage means a signal was measurable. Positive-frame and event rates are observed outputs, not false-positive rates. A missing face may be a detector failure: a wide opening shot visibly contained the candidate while the detector initially found no face. Multiple visible faces can include the interviewer in this camera setup. These events require context.
A qualitative audit inspected six stills per example for six selected events: four event types from the 94-recording snapshot, followed by the full-cohort longest head-change and no-face events. It found visible posture/gaze changes, a no-face event with the candidate still in view, and a multi-face alert with only one apparent face in the inspected stills. This is not a random sample or independent full-clip annotation, so no event precision/FPR is claimed. Aggregate findings: [audit](mit-qualitative-audit-20261029.json).
The final outliers exposed two input problems. A candidate was looking down and writing in the opening baseline; normal upright answering later produced a long head-change event. Another clip contained a long empty-chair period. Therefore the reported full-file event rates describe recording-wide behavior, including non-answer periods. Guided calibration after the candidate is ready and valid answer-window filtering are required before product validation.

## Independent direction-label checks

One known center-gaze image per person is used for calibration and excluded. The remaining 1,120 images from 56 people contain 1,008 direction-deviation positives and 112 central negatives. Neither CNN is fitted on these images; calibration enrolls each person using the known center image.

| Frozen model | Raw forward-distance AUC | Center-calibrated AUC | 95% participant-bootstrap interval |
|---|---:|---:|---|
| MobileOne-S0 | 0.7841 | 0.8824 | 0.8467–0.9126 |
| ResNet-34 | 0.7409 | 0.8422 | 0.7971–0.8848 |

The matched MobileOne-S0 minus ResNet-34 AUC difference is 0.0401; paired participant-bootstrap 95% interval 0.0030–0.0762. On this cohort the larger network did not improve direction discrimination.
These are exploratory component comparisons on a previously examined dataset. This 1,120-image calibration cohort differs from the earlier 1,176-image trained-HGB benchmark. Its AUC must not be presented as interview cheating AUC.

Five known calibration targets were also tried. All five were excluded for every comparator, leaving a separate 896-image cohort. See the aggregate JSON for matched one-/five-point scores, paired bootstrap uncertainty and threshold sensitivity. Those known target labels do not exist in MIT, so the five-point procedure was not applied there.

## Implementation and next experiment

Current video path: frames → MediaPipe face/pose/quality → frozen gaze CNN → baseline-relative changes → sustained event timeline. The frozen camera-relative head/gaze classifiers remain comparison outputs. AI-assistance probability is null.
A natural opening baseline may itself contain off-screen looking. The relative method detects changes, not whether the reference direction is legitimate. A directed calibration is a different protocol and requires fresh validation.
For the product, first identify valid interview/answer windows, add guided calibration after the candidate is ready, and keep candidate-tile selection explicit. Validate timestamps on independent annotated clips, then collect matched unassisted, own-notes and AI-assisted interview recordings before fitting or evaluating an AI-use fusion model. Align review events with the existing ASR/text answer windows.
The Duolingo authors likewise distinguish gaze navigation from screen-location/violation judgments and identify camera/screen calibration as necessary. [Primary paper](https://arxiv.org/html/2409.16923v1). Both compared CNNs are published Gaze360-trained weights from [MobileGaze](https://github.com/yakhyo/gaze-estimation).

MIT source citation: I. Naim, I. Tanveer, D. Gildea and M. E. Hoque, *Automated Analysis and Prediction of Job Interview Performance*, IEEE Transactions on Affective Computing, 2016. [Dataset authors’ project page](https://roc-hci.com/past-projects/automated-prediction-of-job-interview-performances/). The page reports 10.5 hours; the delivered files here total approximately 13.3 hours by local metadata/decoding. No trimming was inferred or silently applied.

## Reproducibility and privacy

- Scripts, fixed settings and commands: [README](../../experiments/video/README.md), [MIT protocol](../../experiments/video/mit_protocol.json).
- Seven focused unit tests passed; two-worker public-video smoke check passed. The full repository suite was not rerun.
- Original media, extracted features, per-recording timelines and weights remain under ignored local data directories. Only aggregate reports/figure are intended for Git.
- Standalone research branch `model/video-behavior-research`; no backend integration or new PR publication in this run.
