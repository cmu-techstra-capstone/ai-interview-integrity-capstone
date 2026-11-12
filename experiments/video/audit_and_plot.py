"""Export lightweight aggregate evidence and a monochrome research figure."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

RAW=Path('data/raw/video_research')
PROCESSED=Path('data/processed/video_research')
REPORT=Path('reports/video')


def main():
    REPORT.mkdir(parents=True,exist_ok=True)
    index=json.loads((RAW/'scenario_subset.json').read_text())
    for item in index['files']:
        actual=hashlib.sha256((RAW/'scenarios'/item['filename']).read_bytes()).hexdigest()
        if actual!=item['content_details']['sha256_hash']:
            raise ValueError('Scenario image/annotation hash mismatch: '+item['filename'])
    cm=json.loads((RAW/'columbia/manifest.json').read_text())
    for item in cm['records']:
        actual=hashlib.sha256((RAW/'columbia'/item['file']).read_bytes()).hexdigest()
        if actual!=item['sha256']:
            raise ValueError('Columbia image hash mismatch: '+item['file'])
    names=['component_metrics','gaze_comparison','columbia_metrics','nested_threshold_metrics']
    results={k:json.loads((PROCESSED/(k+'.json')).read_text()) for k in names}
    summaries={k:json.loads((PROCESSED/k/'timeline.json').read_text()) for k in ['final_demo_default','final_demo_multiface','demo_black']}
    summary={'date':'2026-10-29','results':results,'video_pipeline_checks':summaries,
             'source_note':'Aggregate metrics only. Public images, per-frame features, model weights and row-level results are stored locally in ignored data directories.'}
    (REPORT/'results-20261029.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    audit={'scenario_subset':json.loads((RAW/'download_summary.json').read_text()),
           'verification':{'scenario_images_and_annotations_verified':len(index['files']),
                           'columbia_images_verified':len(cm['records'])},
           'columbia':{k:v for k,v in json.loads((RAW/'columbia/manifest.json').read_text()).items() if k!='records'},
           'models':{name:{'bytes':(Path('data/models/video_research')/name).stat().st_size,
                    'sha256':hashlib.sha256((Path('data/models/video_research')/name).read_bytes()).hexdigest()}
                     for name in ['face_landmarker.task','mobileone_s0_gaze.onnx']}}
    (REPORT/'provenance-20261029.json').write_text(json.dumps(audit,indent=2))
    fig,axes=plt.subplots(1,2,figsize=(10.5,4),layout='constrained')
    ax=axes[0]
    base=results['component_metrics']['tasks']['eye_deviation_when_head_centered']['models']['hist_gradient_boosting']['pooled_oof']['auroc']
    improved=results['gaze_comparison']['tasks']['eye_deviation_when_head_centered']['variants']['mobilegaze/logistic']['pooled_oof']['auroc']
    final=results['nested_threshold_metrics']['models']['combined_balanced_HGB']['pooled_oof']
    vals=[base,improved,final['auroc']]
    bars=ax.bar(['Iris geometry\n3 people','MobileGaze\n3 people','Combined gaze\n56 people'],vals,color=['white','0.7','0.3'],edgecolor='black')
    ax.axhline(.5,color='black',ls='--',lw=.8);ax.set_ylim(0,1);ax.set_ylabel('AUROC');ax.set_title('Eye direction, head held forward')
    for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+.02,f'{v:.3f}',ha='center')
    ax=axes[1];vals=[final['fpr'],final['recall']]
    bars=ax.bar(['False positive rate','Recall'],vals,color=['white','0.5'],edgecolor='black')
    ax.set_ylim(0,1);ax.set_ylabel('Rate');ax.set_title('56 people: nested threshold selection')
    for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+.025,f'{v:.1%}',ha='center')
    fig.suptitle('Eye direction research — two datasets; only the first two bars share a test cohort',fontsize=11)
    fig.savefig(REPORT/'video-results-20261029.png',dpi=180)
    plt.close(fig)
    # Local annotation audit: inspect centered-head eye labels without publishing faces.
    from PIL import Image,ImageDraw
    rows=[json.loads(s) for s in (PROCESSED/'frame_features.jsonl').read_text().splitlines()]
    picked=[]
    for label in range(5,10):
        picked.append(next(r for r in rows if r['head_label']==3 and r['eye_label']==label and r['participant']=='S2'))
    canvas=Image.new('RGB',(1500,240),'white');draw=ImageDraw.Draw(canvas)
    for i,r in enumerate(picked):
        im=Image.open(RAW/'scenarios'/r['file']);im.thumbnail((300,205));canvas.paste(im,(i*300,0))
        draw.text((i*300+4,210),f"eye={r['eye_label']} head=3 {r['file']}",fill='black')
    canvas.save(PROCESSED/'label_audit.png')
    print('Wrote aggregate results, provenance, monochrome figure and a local-only visual label audit.')


if __name__=='__main__':main()
