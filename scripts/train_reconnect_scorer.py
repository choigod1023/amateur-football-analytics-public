"""Train only on fingerprinted, raw-frame human pairs. Never reads evaluation video."""
import argparse,hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.learned_reconnect import descriptor,pair_features,fit_scorer,score
from app.difference_review import fingerprint


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    data=json.loads(a.manifest.read_text(encoding='utf-8'));x=[];y=[];groups=set();audit=[]
    for pair in data['pairs']:
        if sha(pair['answer_path'])!=pair['answer_sha256']:raise ValueError('Answer changed')
        answer=json.loads(Path(pair['answer_path']).read_text(encoding='utf-8'))
        if answer.get('source')!='human' or answer.get('fingerprint')!=pair['fingerprint'] or answer.get('verdict')!=pair['verdict']:raise ValueError('Invalid human answer')
        queue=json.loads((Path(pair['answer_path']).parent.parent/'queue.json').read_text(encoding='utf-8'))
        item=next((r for r in queue['items'] if r['id']==pair['id']),None)
        if item is None or fingerprint(item)!=answer['fingerprint'] or answer['id']!=pair['id']:raise ValueError('Stale scene evidence')
        desc=[]
        for side in ('before','after'):
            row=pair[side]
            if sha(row['frame_path'])!=row['frame_sha256']:raise ValueError('Frame changed')
            frame=cv2.imread(row['frame_path'])
            if frame is None:raise ValueError('Cannot decode raw training frame')
            desc.append(descriptor(frame,row['box_xyxy']))
        features=pair_features(*desc,pair['before']['box_xyxy'],pair['after']['box_xyxy'],pair['after']['source_time_sec']-pair['before']['source_time_sec'])
        if features is None:raise ValueError('Insufficient raw crop pixels')
        x.append(features);y.append(pair['label']);groups.add(pair['video_group']);audit.append({'id':pair['id'],'label':pair['label']})
    model=fit_scorer(x,y)
    model.update({'train_video_groups':sorted(groups),'manifest_sha256':sha(a.manifest),
        'train_frame_hashes':sorted({r[side]['frame_sha256'] for r in data['pairs'] for side in ('before','after')}),
        'operationally_approved':False,'evaluation_policy':'threshold .90 and margin .15 fixed before any heldout evaluation; no holdout tuning'})
    for row,features in zip(audit,x):row['training_score']=score(model,features)
    model['training_diagnostics']=audit
    with a.output.open('x',encoding='utf-8') as f:json.dump(model,f,ensure_ascii=False,indent=2)
    print(json.dumps({'pairs':len(y),'groups':sorted(groups),'training_only':audit,'threshold':model['threshold']}))


if __name__=='__main__':main()
