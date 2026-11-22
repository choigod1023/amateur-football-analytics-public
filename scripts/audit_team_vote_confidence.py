"""Read-only CPU replay of team-vote confidence; no detector or truth mutation.

The candidate is deliberately fixed before evaluation: last 15 observations,
three votes and 2/3 agreement, .5 probability/.1 margin, overlapping shirts
withheld. Coverage is reported alongside wrong accepted classifications.
"""
import argparse
import json
from pathlib import Path
import sys
import cv2
import numpy as np
import torch

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from app.team_role_features import box_features
from app.team_role_infer import load_model, predict, LETTER
from app.identity_guard import _overlap
from retrain_reviewed_team import HELD
from train_team_role import load
from app.team_vote_policy import WindowVote, confident


def main():
    p=argparse.ArgumentParser()
    p.add_argument('observations',type=Path);p.add_argument('video',type=Path)
    p.add_argument('store',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);torch.set_num_threads(2)
    model=load_model(a.model)
    scenes,x,y=load(a.store);mask=np.isin(scenes,list(HELD));prob=predict(model,x[mask]);truth=y[mask]
    guessed=prob.argmax(1);accepted=np.array([confident(row) for row in prob])
    held={'n':len(truth),'argmax_correct':int((guessed==truth).sum()),'confident_n':int(accepted.sum()),
          'confident_correct':int(((guessed==truth)&accepted).sum()),
          'withheld_wrong':int(((guessed!=truth)&~accepted).sum()),'withheld_correct':int(((guessed==truth)&~accepted).sum())}
    log=[json.loads(line) for line in a.observations.read_text(encoding='utf-8').splitlines()]
    cap=cv2.VideoCapture(str(a.video));fps=cap.get(cv2.CAP_PROP_FPS);index=-1;mapping={}
    votes=WindowVote();counts={'frames':0,'baseline_capacity':0,'candidate_capacity_on_baseline_pool':0,
        'baseline_player_samples':0,'retained_same_team_samples':0,'changed_team_samples':0,'withheld_samples':0}
    output=[]
    for r in log:
        target=round(r['time']*fps)
        while index<target:
            if not cap.grab():raise RuntimeError('Video ended before observation')
            index+=1
        ok,frame=cap.retrieve()
        if not ok:raise RuntimeError('Decode failed')
        for event in r.get('identity_events',[]):
            if event.get('action')=='split':mapping[int(event['raw_id'])]=int(event['new_segment'])
        rows=r['source_tracks'];h,w=frame.shape[:2]
        features=np.asarray([box_features(frame,[b[0]/w,b[1]/h,b[2]/w,b[3]/h]) for b in rows])
        probs=predict(model,features) if len(rows) else []
        labels={};diag=[]
        for i,(box,pr) in enumerate(zip(rows,probs)):
            tid=mapping.get(int(box[4]),int(box[4]));letter=LETTER[model['classes'][int(np.argmax(pr))]]
            crowded=any(j!=i and _overlap(box[:4],other[:4])>=.35 for j,other in enumerate(rows))
            label=votes.update(tid,letter if confident(pr) and not crowded else None)
            labels[str(tid)]=label
            diag.append({'id':str(tid),'raw_id':int(box[4]),'prob':list(map(float,pr)),
                         'argmax':letter,'crowded':crowded,'candidate':label,'box':box[:4]})
        counts['frames']+=1;baseline=r.get('unlinked_players',r['players']);candidate=[]
        if any(sum(p['team']==team for p in baseline)>11 for team in ('home','away')):counts['baseline_capacity']+=1
        for person in baseline:
            tid=str(person['id']);label=labels.get(tid);counts['baseline_player_samples']+=1
            if label is None:counts['withheld_samples']+=1;continue
            team='home' if label=='B' else 'away'
            counts['retained_same_team_samples' if team==person['team'] else 'changed_team_samples']+=1
            candidate.append({**person,'team':team})
        if any(sum(p['team']==team for p in candidate)>11 for team in ('home','away')):counts['candidate_capacity_on_baseline_pool']+=1
        output.append({'time':r['time'],'rows':diag,'baseline':baseline,'candidate_on_baseline_pool':candidate})
    cap.release()
    result={'heldout':held,'replay':counts,'limitations':['Replay pool limited to original classified/projected players: not a full new tracking run.',
       'Lower capacity or fewer label changes do not establish correct player identity or team.',
       'Model probabilities are not calibrated confidence; temporal policy not human-GT validated.',
       'No operating configuration changed.']}
    (a.output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (a.output/'predictions.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in output)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
