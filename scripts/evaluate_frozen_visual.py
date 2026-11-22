"""Frozen CPU MobileNet transfer experiment; existing human answers remain read-only."""
import argparse, hashlib, json, sys, time
from pathlib import Path
import cv2
import numpy as np
import torch
sys.path[:0] = [str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from app.team_role_features import box_features
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
from PIL import Image
from app.team_role_features import CLASSES, class_of
from retrain_reviewed_team import HELD, metrics
import train_team_role as train

NEW = {'1da78e7532195a1410c61e3b1cd20a80.jpg','426e7046c075a96dc56a46690aae291b.jpg',
       '63ed34ffc224e22c5cf4839ab2521bd6.jpg','29402e4af63885b062ea6ab06b6a315a.jpg'}
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def frozen_crop(image, bbox, preprocess):
    h,w=image.shape[:2]
    bbox=np.asarray(bbox,dtype=float)
    if bbox.shape!=(4,) or not np.isfinite(bbox).all():raise ValueError('Expected finite normalized xyxy')
    x1,y1,x2,y2=np.clip(bbox,0,1)
    if x2<=x1 or y2<=y1:raise ValueError('Empty or inverted box')
    l,t=int(x1*w),int(y1*h);r,b=max(l+1,int(x2*w)),max(t+1,int(y2*h))
    crop=Image.fromarray(image[t:b,l:r,::-1].copy())
    # Pad to square with central crop clearance, preserving the complete person.
    side=int(np.ceil(max(crop.size)*8/7))+2
    canvas=Image.new('RGB',(side,side),(128,128,128))
    canvas.paste(crop,((side-crop.width)//2,(side-crop.height)//2))
    return preprocess(canvas)

def main():
    p=argparse.ArgumentParser();p.add_argument('store',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    cache=a.output.parent/'torch-cache';cache.mkdir(exist_ok=True)
    torch.hub.set_dir(str(cache))
    weights=MobileNet_V3_Small_Weights.IMAGENET1K_V1
    model=mobilenet_v3_small(weights=weights,progress=False).eval().cpu()
    model.classifier=torch.nn.Identity()
    for parameter in model.parameters():parameter.requires_grad_(False)
    preprocess=weights.transforms()
    torch.set_num_threads(2);cv2.setNumThreads(1)
    hashes={str(f):sha(f) for f in a.store.rglob('*.json')}
    rows=[];images={};started=time.perf_counter()
    for f in sorted(a.store.glob('*.json')):
        try: row=json.loads(f.read_text(encoding='utf-8'))
        except (OSError,ValueError):continue
        if not isinstance(row,dict) or 'bbox_image_norm' not in row:continue
        cls=class_of(row.get('role'),row.get('team_group'))
        if cls is None:continue
        name=row['image']
        if name not in images:images[name]=cv2.imread(str(a.store/name))
        if images[name] is None:continue
        rows.append((name,CLASSES.index(cls),(box_features(images[name],row['bbox_image_norm']),frozen_crop(images[name],row['bbox_image_norm'],preprocess))))
    extraction=time.perf_counter()-started
    scenes=np.array([r[0] for r in rows]);y=np.array([r[1] for r in rows])
    held=np.isin(scenes,list(HELD));new=np.isin(scenes,list(NEW));training=~held
    assert held.sum()==136 and new.sum()==5, (held.sum(),new.sum())
    imagehash={s:sha(a.store/s) for s in set(scenes)}
    assert not {imagehash[s] for s in scenes[held]} & {imagehash[s] for s in scenes[training]}
    with torch.inference_mode():
        embeddings=np.concatenate([model(torch.stack([r[2][1] for r in rows[i:i+16]])).numpy() for i in range(0,len(rows),16)])
    parts=[np.array([r[2][0] for r in rows]),embeddings]
    extraction=time.perf_counter()-started
    weight_file=cache/'checkpoints'/'mobilenet_v3_small-047dcff4.pth'
    manifest={'classes':CLASSES,'label_hashes':hashes,'images':imagehash,'train_rows':int(training.sum()),
        'held_rows':int(held.sum()),'new_training_rows':int(new.sum()),'held_images':sorted(HELD),
        'new_images':sorted(NEW),'hidden':train.HIDDEN,'epochs':train.EPOCHS,'seeds':train.SEEDS,
        'hyperparameters_frozen':True,'device':'cpu','pretrained_weights':weights.url,'weight_sha256':sha(weight_file),'weight_bytes':weight_file.stat().st_size,'frozen_encoder':True,'crop':'square padding then official transforms','torch':torch.__version__}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    results={'extraction_seconds':extraction,'models':{}}
    for name,count in [('frozen_mobilenet_plus24',2)]:
        x=np.concatenate(parts[:count],axis=1);started=time.perf_counter()
        prob,states,mean,spread=train.fit(x[training],y[training],x)
        results['models'][name]={'features':x.shape[1],'fit_predict_seconds':time.perf_counter()-started,
            'heldout':metrics(prob[held],y[held],scenes[held]),'training':metrics(prob[training],y[training],scenes[training]),
            'new_training':metrics(prob[new],y[new],scenes[new]),
            'new_predictions':[{'image':str(s),'truth':CLASSES[int(t)],'prediction':CLASSES[int(v.argmax())],
                 'spectator_probability':float(v[1])} for s,t,v in zip(scenes[new],y[new],prob[new])]}
        torch.save({'states':states,'mean':mean,'spread':spread,'classes':CLASSES,'features':name,'hidden':train.HIDDEN},a.output/(name+'.pt'))
        print(name,results['models'][name]['heldout']['correct'], '/136',flush=True)
    results['source_unchanged']=all(sha(Path(f))==v for f,v in hashes.items()) and all(sha(a.store/s)==v for s,v in imagehash.items())
    results['limitations']=['Four heldout images from two temporal events in one match; not independent match validation.',
        'Frozen ImageNet MobileNetV3-small, not football ReID pretraining or BPBreID reproduction.',
        'Same head optimizer/hyperparameters but feature counts and parameter counts differ. Fixed holdout has now been inspected repeatedly: model selection bias; no independent final test.',
        'New five answers are training data; their success is not generalization.',
        'No detection, identity, goalkeeper-specific or coaching accuracy measured. Context can memorize camera/background.']
    (a.output/'metrics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
