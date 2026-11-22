"""Paired CPU retraining on saved capacity answers, preserving fixed holdout.

New answers are training evidence, never independent evaluation. Exact duplicate
images may occur within training but must not cross the holdout boundary.
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


def partition(scenes, new_images, image_hashes, train_allowed=None):
    scenes=np.asarray(scenes)
    held=np.isin(scenes,list(HELD))
    new=np.isin(scenes,list(new_images))
    if not held.any() or not new.any():
        raise ValueError('Expected existing holdout and newly saved answers')
    if (held & new).any():
        raise ValueError('New training questions overlap heldout images')
    allowed=np.ones(len(scenes),bool) if train_allowed is None else np.asarray(train_allowed,bool)
    if (new & ~allowed).any():
        raise ValueError('New training images are not explicitly in the train split')
    candidate=~held & allowed
    if {image_hashes[s] for s in scenes[candidate]} & {image_hashes[s] for s in scenes[held]}:
        raise ValueError('Duplicate image leaks across the holdout boundary')
    return candidate & ~new,candidate,held,new


def run(store, old, publication, output):
    store,old,publication,output=map(Path,(store,old,publication,output))
    new_images={row['token']+'.jpg' for row in json.loads(publication.read_text(encoding='utf-8'))['items']}
    files=sorted(store.rglob('*.json'))
    hashes={str(p):sha(p) for p in files}
    scenes,x,y=train.load(store);scenes=np.asarray(scenes)
    imagehash={s:sha(store/s) for s in set(scenes)}
    base,candidate,held,new=partition(scenes,new_images,imagehash,train.training_mask(store,scenes))
    source_splits=train.scene_splits(store)
    train.validate_image_split(store,scenes,candidate,held | np.asarray([source_splits[s]=='eval' for s in scenes]))
    if int(held.sum())!=136 or int(new.sum())!=5:
        raise ValueError('Expected the frozen 136-label holdout and exactly five saved new labels')
    output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(2)
    manifest={'classes':list(CLASSES),'held_images':sorted(HELD),'new_images':sorted(new_images),
        'base_rows':int(base.sum()),'candidate_rows':int(candidate.sum()),'held_rows':int(held.sum()),
        'new_rows':int(new.sum()),'images':imagehash,'label_hashes':hashes,
        'old_model_sha256':sha(old),'epochs':train.EPOCHS,'seeds':train.SEEDS,
        'hidden':train.HIDDEN,'hyperparameters_frozen':True,'device':'cpu'}
    manifest['train_images']=sorted(set(scenes[candidate]));manifest['source_splits']=train.scene_splits(store)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    models={'old_deployed':load_model(old)}
    for name,mask in [('matched_baseline',base),('candidate',candidate)]:
        _,states,mean,spread=train.fit(x[mask],y[mask],x[held])
        torch.save({'states':states,'mean':mean,'spread':spread,'classes':list(CLASSES),
            'features':list(FEATURE_NAMES),'hidden':train.HIDDEN},output/(name+'.pt'))
        models[name]=load_model(output/(name+'.pt'))
    results={}
    for name,model in models.items():
        probabilities=predict(model,x[new])
        results[name]={'holdout':metrics(predict(model,x[held]),y[held],scenes[held]),
            'new_training_examples':metrics(probabilities,y[new],scenes[new]),
            'new_predictions':[{'image':str(scene),'truth':CLASSES[int(truth)],
                'prediction':CLASSES[int(prob.argmax())],
                'probabilities':{c:float(v) for c,v in zip(CLASSES,prob)}}
                for scene,truth,prob in zip(scenes[new],y[new],probabilities)]}
    results['source_unchanged']=all(Path(p).exists() and sha(p)==digest for p,digest in hashes.items())
    results['limitations']=[
        'New five labels are trained examples, not independent accuracy evidence.',
        'Fixed 136 labels are four images from two temporal events in one match.',
        'Goalkeeper team A maps to team_a; four-class model cannot separately identify goalkeeper role.',
        'No detector, bounding-box or identity ground-truth accuracy is established by this experiment.',
        'Current live majority votes may disagree with single-frame classifier scores.',
        'Original deployed training manifest is incomplete; paired baseline/candidate exclude the same heldout images.']
    (output/'metrics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    if not results['source_unchanged']:
        raise RuntimeError('Source labels changed during the experiment')
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('store','old','publication','output'):p.add_argument(arg,type=Path)
    a=p.parse_args();r=run(a.store,a.old,a.publication,a.output)
    print(json.dumps({name:{'holdout':v['holdout']['correct'],'held_total':v['holdout']['total'],
                           'new_correct':v['new_training_examples']['correct'],'new_total':v['new_training_examples']['total']}
                      for name,v in r.items() if isinstance(v,dict)}))
