"""Export only aggregate MIT/calibration results and a monochrome figure."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


ROOT=Path('data/processed/video_research')
OUT=Path('reports/video')


def load(path):return json.loads(path.read_text())
def percent(x):return f'{100*x:.2f}%'


def main():
    raw=load(ROOT/'mit_full/summary.json')
    if raw['completed_recordings']!=138 or raw['recordings']!=138 or raw['errors']:
        raise ValueError('Refusing final export: full MIT batch incomplete or contains errors.')
    relative=load(ROOT/'mit_full_relative/summary.json')
    if relative['recordings']!=138:raise ValueError('Relative-event batch incomplete.')
    archive=load(Path('data/raw/video_research/mit/video_archive_inventory.json'))
    archive={k:v for k,v in archive.items() if k!='files'}
    columbia=load(ROOT/'calibration_benchmark/summary.json')
    challenger=load(ROOT/'calibration_resnet34/summary.json')
    challenger_provenance=load(ROOT/'columbia_resnet34.provenance.json')
    comparison=load(ROOT/'calibrated_model_comparison.json')
    qualitative=load(OUT/'mit-qualitative-audit-20261029.json')
    inventory=load(ROOT/'mit_full/inventory.json')
    frame_ms=[]
    duration_differences=[]
    for item in inventory['videos']:
        timeline=load(ROOT/'mit_full'/item['recording_id']/'timeline.json')
        duration_differences.append(abs(timeline['analyzed_seconds']-item['duration_s']))
        for line in (ROOT/'mit_full'/item['recording_id']/'measurements.jsonl').open():
            frame_ms.append(json.loads(line)['inference_ms'])
    if max(duration_differences)>1:
        raise ValueError('Decoded duration differs from source metadata by over 1s; inspect before final export.')
    wall=(ROOT/'mit_full/summary.json').stat().st_mtime-(ROOT/'mit_full/inventory.json').stat().st_mtime
    payload={'mit_archive':archive,'mit_absolute_pipeline':raw,'mit_relative_events':relative,
        'columbia_mobileone_s0':columbia,'columbia_resnet34':challenger,
        'resnet34_provenance':challenger_provenance,
        'paired_model_comparison':comparison,
        'qualitative_audit':qualitative,
        'timing':{'full_batch_approx_wall_seconds':wall,
            'wall_time_basis':'final summary mtime minus initial inventory mtime; excludes acquisition/probe/model preparation',
            'sampled_frame_inference_median_ms':float(np.median(frame_ms)),
            'sampled_frame_inference_p95_ms':float(np.percentile(frame_ms,95)),
            'scope':'Two concurrent CPU workers; full pipeline time also includes decoding, loading and file writes.'},
        'verification':{'focused_unit_tests_passed':7,'parallel_smoke_examples':2,
            'decoded_duration_max_absolute_difference_seconds':max(duration_differences),
            'full_repository_suite_rerun':False},
        'interpretation':'Columbia metrics are gaze-direction metrics. MIT coverage/event counts are unlabeled transfer diagnostics, not cheating accuracy.'}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'mit-video-results-20261029.json').write_text(json.dumps(payload,indent=2,allow_nan=False))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    names=['S0\nraw','S0\ncenter-calibrated','ResNet-34\nraw','ResNet-34\ncenter-calibrated']
    auc=[columbia['raw_forward_distance_auroc_same_scored_cohort'],columbia['relative_to_known_center_auroc'],
         challenger['raw_forward_distance_auroc_same_scored_cohort'],challenger['relative_to_known_center_auroc']]
    bars=axes[0].bar(np.arange(4),auc,color=['white','.7','white','.35'],edgecolor='black')
    axes[0].set(xticks=np.arange(4),xticklabels=names,ylim=(0,1),ylabel='AUROC',title='Gaze direction: same 1,120-image cohort')
    axes[0].axhline(.5,color='.5',linestyle='--',linewidth=.8)
    for bar,value in zip(bars,auc):axes[0].text(bar.get_x()+bar.get_width()/2,value+.015,f'{value:.3f}',ha='center')
    x=np.arange(2);before=[relative['absolute_signal_coverage_same_evaluation_period'][k]['measured_fraction']*100 for k in ['head_deviation','eye_deviation']]
    after=[relative['signal_coverage'][k]['measured_fraction']*100 for k in ['head_deviation','eye_deviation']]
    for offset,values,color,label in [(-.19,before,'white','Absolute pipeline'),(.19,after,'.5','Relative pipeline')]:
        bars=axes[1].bar(x+offset,values,width=.38,color=color,edgecolor='black',label=label)
        for bar,value in zip(bars,values):axes[1].text(bar.get_x()+bar.get_width()/2,value+1,f'{value:.1f}%',ha='center')
    axes[1].set(xticks=x,xticklabels=['Head signal','Gaze signal'],ylim=(0,110),ylabel='Measured evaluation frames (%)',title='MIT: coverage after first 30 seconds')
    axes[1].legend(loc='upper center',bbox_to_anchor=(.5,-.1),ncol=2,frameon=False)
    fig.suptitle('Video research: direction validation and interview-domain transfer',fontsize=14)
    fig.savefig(OUT/'mit-video-results-20261029.png',dpi=180,bbox_inches='tight');plt.close(fig)
    lines=['# MIT video transfer and calibrated gaze results — 2026-10-29','',
        'The complete MIT archive was processed locally. The main finding is that camera-relative direction rules do not transfer directly to oblique interview footage. Personal calibration is useful for direction scoring; it does not establish AI-assistance detection.','',
        '## Data and execution','',
        f'- MIT: {archive["videos"]} videos from {archive["participants"]} people; {raw["analyzed_seconds"]/3600:.2f} analyzed hours; 640 × 480, 29 fps source.',
        f'- Archive: {archive["archive_bytes"]:,} bytes; CRC passed for all AVI members; SHA-256 `{archive["archive_sha256"]}`.',
        f'- Full run: 2 sampled frames/second, two workers, {raw["sampled_frames"]:,} measurements, zero processing errors.',
        '- Fixed engineering pilot: first 60 seconds of six pre/post counseling recordings, 5 fps. All 1,695 measurable head frames triggered the absolute model; gaze coverage was zero.',
        '- Full processing uses the original frozen MobileOne-S0 measurements. No MIT ratings were converted into AI-use labels, and no AI-use classifier was trained on MIT.','',
        '## MIT transfer results','',
        'The exploratory relative method uses only the first 30 seconds to estimate a rotation medoid and a typical gaze vector. Those seconds are excluded from evaluation. At least 10 valid calibration samples are required. Estimated direction changes must exceed 15° for at least 2 seconds. This is an unlabeled natural baseline, not a directed screen calibration.','',
        '| Measure | Result |','|---|---|',
        f'| Evaluation after calibration | {relative["evaluation_seconds"]/3600:.2f} hours; {relative["evaluation_frames"]:,} sampled frames |',
        f'| Head/gaze baseline available | {relative["recordings_with_head_baseline"]}/138; {relative["recordings_with_gaze_baseline"]}/138 recordings |']
    for task,label in [('head_deviation','Head'),('eye_deviation','Gaze')]:
        a=relative['absolute_signal_coverage_same_evaluation_period'][task];b=relative['signal_coverage'][task]
        lines += [f'| {label} measurable coverage, absolute → relative | {percent(a["measured_fraction"])} → {percent(b["measured_fraction"])} |',
                  f'| Relative {label.lower()} positive frames / measurable frames | {b["positive_frames"]:,}/{b["measured_frames"]:,} ({percent(b["positive_fraction_of_measured"])}) |']
    lines += [f'| Observed sustained events | `{json.dumps(relative["event_counts"],sort_keys=True)}` |',
        f'| Batch approximate wall time | {wall/60:.1f} minutes; excludes download/probing |',
        f'| Sample inference median / P95 | {np.median(frame_ms):.1f} / {np.percentile(frame_ms,95):.1f} ms with two workers |','',
        'Coverage means a signal was measurable. Positive-frame and event rates are observed outputs, not false-positive rates. A missing face may be a detector failure: a wide opening shot visibly contained the candidate while the detector initially found no face. Multiple visible faces can include the interviewer in this camera setup. These events require context.',
        'A qualitative audit inspected six stills per example for six selected events: four event types from the 94-recording snapshot, followed by the full-cohort longest head-change and no-face events. It found visible posture/gaze changes, a no-face event with the candidate still in view, and a multi-face alert with only one apparent face in the inspected stills. This is not a random sample or independent full-clip annotation, so no event precision/FPR is claimed. Aggregate findings: [audit](mit-qualitative-audit-20261029.json).',
        'The final outliers exposed two input problems. A candidate was looking down and writing in the opening baseline; normal upright answering later produced a long head-change event. Another clip contained a long empty-chair period. Therefore the reported full-file event rates describe recording-wide behavior, including non-answer periods. Guided calibration after the candidate is ready and valid answer-window filtering are required before product validation.','',
        '## Independent direction-label checks','',
        'One known center-gaze image per person is used for calibration and excluded. The remaining 1,120 images from 56 people contain 1,008 direction-deviation positives and 112 central negatives. Neither CNN is fitted on these images; calibration enrolls each person using the known center image.','',
        '| Frozen model | Raw forward-distance AUC | Center-calibrated AUC | 95% participant-bootstrap interval |','|---|---:|---:|---|']
    for name,r in [('MobileOne-S0',columbia),('ResNet-34',challenger)]:
        ci=r['participant_bootstrap_95_interval'];op=r['operating_points_degrees']['10']
        lines += [f'| {name} | {r["raw_forward_distance_auroc_same_scored_cohort"]:.4f} | {r["relative_to_known_center_auroc"]:.4f} | {ci[0]:.4f}–{ci[1]:.4f} |']
    delta_ci=comparison['paired_participant_bootstrap_95_delta']
    lines += ['',
        f'The matched MobileOne-S0 minus ResNet-34 AUC difference is {comparison["mobileone_minus_resnet_auc"]:.4f}; paired participant-bootstrap 95% interval {delta_ci[0]:.4f}–{delta_ci[1]:.4f}. On this cohort the larger network did not improve direction discrimination.',
        'These are exploratory component comparisons on a previously examined dataset. This 1,120-image calibration cohort differs from the earlier 1,176-image trained-HGB benchmark. Its AUC must not be presented as interview cheating AUC.','',
        'Five known calibration targets were also tried. All five were excluded for every comparator, leaving a separate 896-image cohort. See the aggregate JSON for matched one-/five-point scores, paired bootstrap uncertainty and threshold sensitivity. Those known target labels do not exist in MIT, so the five-point procedure was not applied there.','',
        '## Implementation and next experiment','',
        'Current video path: frames → MediaPipe face/pose/quality → frozen gaze CNN → baseline-relative changes → sustained event timeline. The frozen camera-relative head/gaze classifiers remain comparison outputs. AI-assistance probability is null.',
        'A natural opening baseline may itself contain off-screen looking. The relative method detects changes, not whether the reference direction is legitimate. A directed calibration is a different protocol and requires fresh validation.',
        'For the product, first identify valid interview/answer windows, add guided calibration after the candidate is ready, and keep candidate-tile selection explicit. Validate timestamps on independent annotated clips, then collect matched unassisted, own-notes and AI-assisted interview recordings before fitting or evaluating an AI-use fusion model. Align review events with the existing ASR/text answer windows.',
        'The Duolingo authors likewise distinguish gaze navigation from screen-location/violation judgments and identify camera/screen calibration as necessary. [Primary paper](https://arxiv.org/html/2409.16923v1). Both compared CNNs are published Gaze360-trained weights from [MobileGaze](https://github.com/yakhyo/gaze-estimation).','',
        'MIT source citation: I. Naim, I. Tanveer, D. Gildea and M. E. Hoque, *Automated Analysis and Prediction of Job Interview Performance*, IEEE Transactions on Affective Computing, 2016. [Dataset authors’ project page](https://roc-hci.com/past-projects/automated-prediction-of-job-interview-performances/). The page reports 10.5 hours; the delivered files here total approximately 13.3 hours by local metadata/decoding. No trimming was inferred or silently applied.','',
        '## Reproducibility and privacy','',
        '- Scripts, fixed settings and commands: [README](../../experiments/video/README.md), [MIT protocol](../../experiments/video/mit_protocol.json).',
        '- Seven focused unit tests passed; two-worker public-video smoke check passed. The full repository suite was not rerun.',
        '- Original media, extracted features, per-recording timelines and weights remain under ignored local data directories. Only aggregate reports/figure are intended for Git.',
        '- Standalone research branch `model/video-behavior-research`; no backend integration or new PR publication in this run.','']
    (OUT/'mit-video-transfer-20261029.md').write_text('\n'.join(lines))
    print('Published aggregate report, JSON and monochrome PNG under reports/video/.')


if __name__=='__main__':main()
