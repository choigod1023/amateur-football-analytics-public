"""Read-only paired role training with declared split and temporal separation.

The old source-eval labels were consumed by earlier training. This repairs the
experiment, not their historical independence; no fresh held-out claim is made.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import train_team_role as train
from retrain_reviewed_team import HELD, metrics
from app.team_role_features import CLASSES, FEATURE_NAMES
from app.team_role_infer import load_model, predict


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def temporal_partition(scenes, metadata, hashes, buffer_seconds=60.):
    """Require explicit train/eval, known same-timeline times, and safe buffers."""
    scenes=np.asarray(scenes)
    held=np.asarray([metadata[s]['split']=='eval' for s in scenes])
    if not held.any():raise ValueError('No declared evaluation images')
    eval_hashes={hashes[s] for s in scenes[held]}
    eval_rows=[metadata[s] for s in set(scenes[held])]
    if any(e.get('time') is None or not np.isfinite(e['time']) or not e.get('clip') for e in eval_rows):
        raise ValueError('Evaluation time/clip provenance is incomplete')
    accepted=[]
    for s in scenes:
        row=metadata[s];t=row.get('time');clip=row.get('clip')
        allowed=(row['split']=='train' and t is not None and np.isfinite(t) and clip
                 and hashes[s] not in eval_hashes)
        if allowed:
            allowed=not any(e.get('clip')==clip and e.get('time') is not None
                            and abs(t-e['time']) < buffer_seconds for e in eval_rows)
        accepted.append(bool(allowed))
    return np.asarray(accepted),held


def read_metadata(store, scenes):
    splits=train.scene_splits(store); grouped={s:[] for s in set(scenes)}
    for p in sorted(store.glob('*.json')):
        row=json.loads(p.read_text(encoding='utf-8'))
        if isinstance(row,dict) and 'bbox_image_norm' in row and row['image'] in grouped:
            grouped[row['image']].append(row)
    result={}
    for scene,rows in grouped.items():
        times={r.get('source_provenance',{}).get('clip_time_sec') for r in rows}
        clips={r.get('source_provenance',{}).get('clip') for r in rows}
        result[scene]={'split':splits[scene], 'time':next(iter(times)) if len(times)==1 else None,
                       'clip':next(iter(clips)) if len(clips)==1 else None,
                       'source':rows[0].get('source'), 'label_files':[]}
        # Capacity review carries the same stitched timeline but omits clip name.
        # Do not infer one from its timestamp: unknown provenance stays excluded.
    return result


def run(store, output):
    store,output=Path(store),Path(output);output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(2)
    labels={str(p):sha(p) for p in store.rglob('*.json')}
    scenes,x,y=train.load(store);scenes=np.asarray(scenes)
    metadata=read_metadata(store,scenes);hashes={s:sha(store/s) for s in set(scenes)}
    clean,held=temporal_partition(scenes,metadata,hashes)
    legacy=~np.isin(scenes,list(HELD))
    # Matched ablation: extra hard-case scenes are fixed by provenance, not test score.
    hard=np.asarray([metadata[s]['source']=='own_match_clip_frame_hard_case' for s in scenes])
    baseline=clean & ~hard
    if any(len(set(y[m]))!=len(CLASSES) for m in (baseline,clean)):
        raise ValueError('Each paired training split must contain every role class')
    manifest={'classes':list(CLASSES),'features':list(FEATURE_NAMES),'epochs':train.EPOCHS,'seeds':train.SEEDS,
              'hidden':train.HIDDEN,'device':'cpu','temporal_buffer_s':60,
              'images':{s:{**metadata[s],'sha256':hashes[s]} for s in sorted(metadata)},
              'label_sha256':labels,'source_code_sha256':{p:sha(Path(__file__).parent/p) for p in ('train_team_role.py','evaluate_own_role_split.py')},
              'eval_images':sorted(set(scenes[held])),'models':{}}
    results={'split_audit':{'usable_rows':len(y),'source_eval_rows':int(held.sum()),
                            'legacy_train_eval_overlap_rows':int((legacy & held).sum()),
                            'strict_train_rows':int(clean.sum()),'strict_baseline_rows':int(baseline.sum()),
                            'excluded_rows':int((~held & ~clean).sum())}}
    for name,mask in [('legacy_leaky_diagnostic',legacy),('clean_baseline',baseline),('clean_candidate',clean)]:
        prob,states,mean,spread=train.fit(x[mask],y[mask],x[held])
        path=output/(name+'.pt')
        torch.save({'states':states,'mean':mean,'spread':spread,'classes':list(CLASSES),
                    'features':list(FEATURE_NAMES),'hidden':train.HIDDEN},path)
        results[name]=metrics(prob,y[held],scenes[held])
        manifest['models'][name]={'train_images':sorted(set(scenes[mask])),'train_rows':int(mask.sum()),
                                 'model_sha256':sha(path),'historical_eval_leakage':bool((mask & held).any())}
        print(name,results[name]['correct'],results[name]['total'],flush=True)
    results['source_unchanged']=all(Path(p).exists() and sha(p)==h for p,h in labels.items())
    results['limitations']=['Existing development labels, previously used by other models; not untouched evaluation.',
        'Legacy diagnostic knowingly trains on evaluation rows; never a valid generalization score.',
        'Clean paired fits exclude all source eval, exact duplicate images and train frames within 60 seconds.',
        'Same match, correlated frames; per-box accuracy is not identity tracking or minimap accuracy.',
        'Goalkeepers are collapsed into team classes. Unknown, duplicate and shadow labels do not train this classifier.',
        'Missing source times or clip identifiers are excluded instead of guessing their provenance.',
        'No operational model replacement or server restart.']
    manifest['metrics_file']='metrics.json'
    (output/'metrics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest['metrics_sha256']=sha(output/'metrics.json')
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('store',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.store,a.output)
