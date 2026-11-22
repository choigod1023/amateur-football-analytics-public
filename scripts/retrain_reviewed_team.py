"""Frozen paired experiment: same architecture/seeds, existing held-out images excluded."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import train_team_role as train
from app.team_role_features import CLASSES,FEATURE_NAMES
from app.team_role_infer import load_model,predict

HELD = {'3497c902db2f1c80694c75d945b35cb2.jpg','6ac3676ac75980da73194b4c525e4141.jpg',
        'b3a9c4c440e6233d32831d88d3e674c9.jpg','cf1e992d269f986ebd9fc79d56472412.jpg'}
NEW = {'50ffaf7e5a16e7bba718aaad4a5e9082.jpg','54e189b7dcaec946540ca4cb45e6f42c.jpg','e8afb4a61a95d1b5768f5b7211e2c3b9.jpg'}


def partition(scenes, train_allowed=None):
    scenes=np.asarray(scenes)
    held=np.isin(scenes,list(HELD));recent=np.isin(scenes,list(NEW))
    if not held.any() or not recent.any():raise ValueError('Expected held-out and recent labels')
    allowed=np.ones(len(scenes),bool) if train_allowed is None else np.asarray(train_allowed,bool)
    if (recent & ~allowed).any():raise ValueError('Recent training images are not explicitly in the train split')
    return ~held & ~recent & allowed, ~held & allowed, held


def metrics(prob,y,scenes):
    guess=prob.argmax(1);conf=np.zeros((len(CLASSES),len(CLASSES)),int)
    for truth,pred in zip(y,guess):conf[truth,pred]+=1
    order=np.sort(prob,axis=1);accept=(order[:,-1]>=.5)&((order[:,-1]-order[:,-2])>=.1)
    return {'correct':int((guess==y).sum()),'total':len(y),'accuracy':float((guess==y).mean()),
        'recall':{c:float((guess[y==k]==k).mean()) if (y==k).any() else None for k,c in enumerate(CLASSES)},
        'confusion':conf.tolist(),'accepted':int(accept.sum()),'accepted_correct':int(((guess==y)&accept).sum()),
        'per_scene':{s:{'correct':int(((guess==y)&(scenes==s)).sum()),'total':int((scenes==s).sum())} for s in sorted(set(scenes))}}


def main():
    p=argparse.ArgumentParser();p.add_argument('store',type=Path);p.add_argument('old',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(2)
    files=list(a.store.rglob('*.json'));hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    scenes,x,y=train.load(a.store);scenes=np.asarray(scenes);base,candidate,held=partition(scenes,train.training_mask(a.store,scenes))
    # Exact duplicate image leakage is forbidden even when filenames differ.
    imagehash={s:hashlib.sha256((a.store/s).read_bytes()).hexdigest() for s in set(scenes)}
    source_splits=train.scene_splits(a.store)
    train.validate_image_split(a.store,scenes,candidate,held | np.asarray([source_splits[s]=='eval' for s in scenes]))
    assert not {imagehash[s] for s in scenes[candidate]} & {imagehash[s] for s in scenes[held]}
    manifest={'classes':list(CLASSES),'held_images':sorted(HELD),'new_images':sorted(NEW),
        'base_rows':int(base.sum()),'candidate_rows':int(candidate.sum()),'held_rows':int(held.sum()),
        'images':imagehash,'label_hashes':hashes,'old_model_sha256':hashlib.sha256(a.old.read_bytes()).hexdigest(),
        'epochs':train.EPOCHS,'seeds':train.SEEDS,'hyperparameters_frozen':True}
    manifest['train_images']=sorted(set(scenes[candidate]));manifest['source_splits']=train.scene_splits(a.store)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    results={'old_deployed':metrics(predict(load_model(a.old),x[held]),y[held],scenes[held])}
    for name,mask in [('matched_baseline',base),('candidate',candidate)]:
        probs,states,mean,spread=train.fit(x[mask],y[mask],x[held])
        results[name]=metrics(probs,y[held],scenes[held])
        torch.save({'states':states,'mean':mean,'spread':spread,'classes':list(CLASSES),
            'features':list(FEATURE_NAMES),'hidden':train.HIDDEN},a.output/(name+'.pt'))
        results[name]['recent_training_examples']=metrics(predict(load_model(a.output/(name+'.pt')),x[np.isin(scenes,list(NEW))]),y[np.isin(scenes,list(NEW))],scenes[np.isin(scenes,list(NEW))])
    results['source_unchanged']=all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==v for f,v in hashes.items())
    results['limitations']=['4 images from 2 temporal events in one match; not 136 independent trials.',
        'Old model lacks complete training manifest; paired baseline/candidate have explicit identical held-out exclusion.',
        'Goalkeepers are folded into team classes. No detector/re-ID training and no identity or coaching accuracy claim.']
    (a.output/'metrics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:{x:v[x] for x in ('correct','total','accuracy','accepted','accepted_correct')} for k,v in results.items() if isinstance(v,dict)}))


if __name__=='__main__':main()
