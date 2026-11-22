"""CPU paired replay of original votes and gap-reset votes on saved tracker rows.

Uses existing classified/projected positions only for the capacity/coaching pool;
does not recover positions that the original classifier omitted.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np
import torch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from app.team_role_features import box_features, class_of
from app.team_role_infer import load_model, predict, LETTER
from compare_capacity_coaching import evaluate


class ReplayVotes:
    def __init__(self, max_gap=None):
        self.max_gap=max_gap;self.last={};self.counts={};self.resets=0

    def update(self, tid, t, letter):
        old=self.last.get(tid)
        if old is not None and self.max_gap is not None and (t<=old or t-old>self.max_gap+1e-7):
            self.counts.pop(tid,None);self.resets+=1
        self.last[tid]=t
        if letter:self.counts.setdefault(tid,Counter())[letter]+=1
        counts=self.counts.get(tid)
        winner,n=counts.most_common(1)[0] if counts else (None,0)
        return {'winner':winner if n>=3 else None,'team':winner if n>=3 and winner in ('A','B') else None,
                'votes':n,'observations':sum(counts.values()) if counts else 0}


def iou(a,b):
    inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    area=lambda x:max(0,x[2]-x[0])*max(0,x[3]-x[1])
    return inter/max(1e-9,area(a)+area(b)-inter)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('observations','video','store','publication','old','candidate','output'):p.add_argument(arg,type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);torch.set_num_threads(2)
    tokens={i['token']+'.jpg' for i in json.loads(a.publication.read_text(encoding='utf-8'))['items']}
    source_hash=hashlib.sha256(a.video.read_bytes()).hexdigest();truth=[]
    for path in a.store.glob('*.json'):
        d=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(d,dict) or d.get('image') not in tokens:continue
        pr=d['source_provenance']
        if pr['source_sha256']!=source_hash:raise ValueError('Human answer source differs from replay')
        truth.append({'time':pr['source_time_sec'],'id':d['track_id'],'role':d['role'],
                      'class':class_of(d['role'],d['team_group']),'box_norm':d['bbox_image_norm']})
    assert len(truth)==5
    logs=[json.loads(s) for s in a.observations.read_text(encoding='utf-8').splitlines()]
    models={k:load_model(v) for k,v in [('old',a.old),('candidate',a.candidate)]}
    configs={'old_votes':('old',ReplayVotes()),'gap_old':('old',ReplayVotes(.6)),
             'gap_candidate':('candidate',ReplayVotes(.6))}
    output={k:[] for k in configs};answers={k:[] for k in configs};features_cache=[]
    cap=cv2.VideoCapture(str(a.video));fps=cap.get(cv2.CAP_PROP_FPS);index=-1;mapping={}
    if not cap.isOpened() or fps<=0:raise ValueError('Invalid replay video')
    for row in logs:
        t=row['time'];target=round(t*fps)
        while index<target:
            if not cap.grab():raise RuntimeError('Video ended before logs')
            index+=1
        ok,frame=cap.retrieve()
        if not ok:raise RuntimeError('Video decode failure')
        h,w=frame.shape[:2];tracks=row['source_tracks']
        for event in row.get('identity_events',[]):
            if event.get('action')=='split':mapping[int(event['raw_id'])]=int(event['new_segment'])
        features=np.asarray([box_features(frame,[b[0]/w,b[1]/h,b[2]/w,b[3]/h]) for b in tracks])
        probabilities={key:predict(model,features) if len(tracks) else [] for key,model in models.items()}
        features_cache.append({'time':t,'tracks':tracks,'features':features.tolist()})
        for name,(model_name,votes) in configs.items():
            decisions={};model=models[model_name]
            for box,prob in zip(tracks,probabilities[model_name]):
                tid=str(mapping.get(int(box[4]),int(box[4])))
                letter=LETTER[model['classes'][int(np.argmax(prob))]]
                decision=votes.update(tid,t,letter)
                decisions[tid]=decision
                for answer in truth:
                    if abs(answer['time']-t)>1e-7 or str(answer['id'])!=tid:continue
                    expected=LETTER[answer['class']]
                    truth_box=np.asarray(answer['box_norm'])*[w,h,w,h]
                    overlap=iou(box[:4],truth_box)
                    if overlap<.9:raise ValueError('Reviewed box is not reproduced at exact frame')
                    answers[name].append({**answer,**decision,'source_box_iou':overlap,
                        'argmax':letter,'probabilities':{cls:float(v) for cls,v in zip(model['classes'],prob)},
                        'correct':decision['winner']==expected,'withheld':decision['winner'] is None})
            base=row.get('unlinked_players',row['players']);people=[]
            for person in base:
                label=decisions.get(str(person['id']),{}).get('team')
                if label:people.append({**person,'team':'home' if label=='B' else 'away'})
            output[name].append({'time':t,'people':people,'original_people':base})
    cap.release()
    result={}
    for name,rows in output.items():
        same=changed=withheld=0
        for row in rows:
            labels={p['id']:p['team'] for p in row['people']}
            for person in row['original_people']:
                if person['id'] not in labels:withheld+=1
                elif person['team']==labels[person['id']]:same+=1
                else:changed+=1
        assert len(answers[name])==5
        result[name]={'resets':configs[name][1].resets,'same_team_samples':same,'changed_team_samples':changed,
            'withheld_samples':withheld,'reviewed_correct':sum(d['correct'] for d in answers[name]),
            'reviewed_withheld':sum(d['withheld'] for d in answers[name]),'reviewed_total':len(answers[name]),
            'reviewed_answers':answers[name],'coaching':evaluate(rows,'people')}
        (a.output/(name+'-rows.jsonl')).write_text('\n'.join(json.dumps(r) for r in rows)+'\n',encoding='utf-8')
    result['limitations']=['Classified/projected baseline pool only; omitted positions not added.',
        'Five reviewed frames are development/training evidence, not independent evaluation.',
        'Goalkeeper class is folded into team A; correct team does not establish correct role.',
        'No full-person count, IDSW, box precision, pitch accuracy or tactical event truth available.']
    (a.output/'features.jsonl').write_text('\n'.join(json.dumps(r) for r in features_cache)+'\n',encoding='utf-8')
    (a.output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({name:{k:v[k] for k in ['resets','same_team_samples','changed_team_samples','withheld_samples','reviewed_correct','reviewed_withheld']} for name,v in result.items() if isinstance(v,dict)}))


if __name__=='__main__':main()
