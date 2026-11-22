"""Train a within-match team metric on OTHER games; evaluate target online clustering.

Other-game GT supervision trains pair similarity, never absolute team numbers.
The target's initial detection crops fit clusters without labels. Target labels
map the arbitrary cluster IDs and tune rejection only on the dev time segment;
the later target time segment is held out. No data leaves this computer.
"""
import argparse, collections, json, random, sys
from pathlib import Path
import cv2, numpy as np, torch
from torch import nn
from ultralytics import YOLO
from torchvision.models import resnet18, ResNet18_Weights
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.team_suggestions import TeamSuggestions, shirt_histogram
from app.tiled_tracking import TiledPlayerTracker
from scripts.evaluate_wide_team_gt import scan
from scripts.evaluate_wide_team_detected import match


def other_game(video, labels):
    d=json.loads(labels.read_text(encoding='utf-8-sig'))
    counts=collections.Counter(p.get('team') for p in d['playerInfo'] if p.get('player_position') in ('DF','MF','FW') and p.get('team'))
    team=[x for x,_ in counts.most_common(2)]
    if len(team)!=2:raise ValueError('Other-game labels do not contain two teams')
    mapping={p['player_sid']:team.index(p['team']) for p in d['playerInfo'] if p.get('player_position') in ('DF','MF','FW') and p.get('team') in team}
    frames={int(t['frame']):t['data'] for t in d['tag']}
    cap=cv2.VideoCapture(str(video)); samples=[]
    for index in range(0, min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 3000), 100):
        if index not in frames:continue
        cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,frame=cap.read()
        if not ok:continue
        for item in frames[index]:
            if item.get('id') not in mapping or len(item.get('tag',[]))!=4:continue
            x,y,w,h=map(float,item['tag']); feat=learned_crop(frame,[x,y,x+w,y+h])
            if feat is not None:samples.append((feat,mapping[item['id']]))
    cap.release()
    return samples


_extractor = None
def learned_crop(frame, box):
    global _extractor
    if _extractor is None:
        torch.hub.set_dir(str((Path(__file__).resolve().parents[3] / 'work/team-feature-pretrain-torch/hub').resolve()))
        _extractor=resnet18(weights=ResNet18_Weights.DEFAULT,progress=False)
        _extractor.fc=nn.Identity();_extractor.eval()
    x1,y1,x2,y2=map(int,box);h,w=frame.shape[:2]
    x1,y1,x2,y2=max(0,x1),max(0,y1),min(w,x2),min(h,y2)
    if x2-x1<12 or y2-y1<30:return None
    crop=frame[y1+int((y2-y1)*.15):y1+int((y2-y1)*.55),x1+int((x2-x1)*.15):x1+int((x2-x1)*.85)]
    if crop.size<30:return None
    crop=cv2.cvtColor(cv2.resize(crop,(96,96)),cv2.COLOR_BGR2RGB)
    t=torch.tensor(crop.transpose(2,0,1),dtype=torch.float32).div_(255.)
    t=(t-torch.tensor([.485,.456,.406])[:,None,None])/torch.tensor([.229,.224,.225])[:,None,None]
    with torch.no_grad():return _extractor(t[None]).flatten().numpy()

class Encoder(nn.Module):
    def __init__(self):
        super().__init__();self.net=nn.Sequential(nn.Linear(512,64),nn.ReLU(),nn.Linear(64,8))
    def forward(self,x):return torch.nn.functional.normalize(self.net(x),dim=-1)


def train(games):
    torch.manual_seed(19);random.seed(19);torch.set_num_threads(2)
    grouped=[]
    for game in games:
        grouped.append([np.asarray([x for x,t in game if t==c],dtype=np.float32) for c in (0,1)])
    if any(min(len(c) for c in g)<10 for g in grouped):raise ValueError('Insufficient other-game team crops')
    model=Encoder();opt=torch.optim.Adam(model.parameters(),lr=.003,weight_decay=.0001)
    for _ in range(400):
        left=[];right=[];same=[]
        for _ in range(128):
            g=random.choice(grouped);a=random.randrange(2);b=a if random.random()<.5 else 1-a
            left.append(g[a][random.randrange(len(g[a]))]);right.append(g[b][random.randrange(len(g[b]))]);same.append(float(a==b))
        x=model(torch.tensor(np.asarray(left)));y=model(torch.tensor(np.asarray(right)));truth=torch.tensor(same)
        similarity=(x*y).sum(dim=1);loss=(truth*(1-similarity)+(1-truth)*torch.relu(similarity-.2)**2).mean()
        opt.zero_grad();loss.backward();opt.step()
    model.eval();return model


def embed(model, feat):
    if feat is None:return None
    with torch.no_grad():return model(torch.tensor(feat,dtype=torch.float32)).numpy()


def score(rows, method, mapping, threshold):
    c=collections.Counter()
    for features,team,baseline in rows:
        if method=='baseline': pred=baseline
        elif features is None:pred=None
        else:
            emb,centres=features;dist=np.linalg.norm(centres-emb[None,:],axis=1); pred=int(np.argmin(dist)) if dist.min() <= threshold else None
        if team is None:c['unmatched_detection']+=1;c['unmatched_assigned']+=int(pred is not None)
        else:
            c['matched']+=1;c['unknown' if pred is None else ('correct' if pred^mapping==team else 'wrong')]+=1
    return dict(c)


def main():
    p=argparse.ArgumentParser();p.add_argument('--other-video',type=Path,nargs=2,required=True);p.add_argument('--other-labels',type=Path,nargs=2,required=True);p.add_argument('--target',type=Path,required=True);p.add_argument('--weights',type=Path,required=True);p.add_argument('--frames',type=int,default=40);p.add_argument('--device',default='cpu');a=p.parse_args()
    games=[other_game(v,l) for v,l in zip(a.other_video,a.other_labels)]
    encoder=train(games);detector=YOLO(str(a.weights));tracker=TiledPlayerTracker(detector,a.device,640,.35);baseline=TeamSuggestions();by_id=collections.defaultdict(list)
    for frame,_,_ in scan(a.target,'0000_0030',range(1,11)):
        tracks=tracker.update(frame);baseline.update(frame,tracks)
        for box,tid in tracks:
            feat=learned_crop(frame,box)
            if feat is not None:by_id[str(tid)].append(feat)
    if baseline.centres is None:raise ValueError('Baseline failed to initialize')
    prototypes=[embed(encoder,np.median(np.stack(x),axis=0)) for x in by_id.values() if x]
    if len(prototypes)<4:raise ValueError('Insufficient unlabeled target tracks')
    cv2.setRNGSeed(19)
    _,clusters,centres=cv2.kmeans(np.asarray(prototypes,dtype=np.float32),2,None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,100,.00001),10,cv2.KMEANS_PP_CENTERS)
    if min(np.bincount(clusters.flatten(),minlength=2))<2:raise ValueError('Unbalanced target clusters')
    def collect(segment,start):
        tracker=TiledPlayerTracker(detector,a.device,640,.35);rows=[];missing=0
        for frame,gt,truth in scan(a.target,segment,range(start,start+a.frames)):
            tracks=tracker.update(frame);matched,n=match(tracks,gt,truth);missing+=n
            for i,(box,tid) in enumerate(tracks):
                feat=learned_crop(frame,box);embedding=embed(encoder,feat)
                rows.append((None if embedding is None else (embedding,centres),matched.get(i),baseline._classify(shirt_histogram(frame,box))))
        return rows,missing
    dev,dev_miss=collect('0060_0090',101);test,test_miss=collect('0120_0150',1)
    # The dev GT is only for evaluation: selecting the arbitrary group↔team
    # permutation and a distance limit. Target labels never train the encoder.
    def mapping(rows,method):
        direct=score(rows,method,0,float('inf')).get('correct',0)
        flipped=score(rows,method,1,float('inf')).get('correct',0)
        return int(flipped>direct)
    base_map=mapping(dev,'baseline');learned_map=mapping(dev,'learned')
    base_dev=score(dev,'baseline',base_map,0);base_test=score(test,'baseline',base_map,0)
    gates=[.05,.1,.2,.3,.4,.5,.7,1.,1.5,2.]
    trials=[(gate,score(dev,'learned',learned_map,gate)) for gate in gates]
    viable=[(g,c) for g,c in trials if c.get('wrong',0)<=base_dev.get('wrong',0) and c.get('unmatched_assigned',0)<=base_dev.get('unmatched_assigned',0)]
    best=max(viable,key=lambda item:item[1].get('correct',0)) if viable else None
    print(json.dumps({'pretraining_game_samples':[len(g) for g in games],'target_unlabeled_tracks':len(prototypes),'target_dev_mapping':{'baseline':base_map,'learned':learned_map},'dev_baseline':base_dev,'dev_gates':{str(g):c for g,c in trials},'selected_gate':None if best is None else best[0],'heldout_baseline':base_test,'heldout_learned':None if best is None else score(test,'learned',learned_map,best[0]),'dev_missing_gt':dev_miss,'heldout_missing_gt':test_miss,'feature':'ImageNet ResNet18 frozen encoder, 96x96 shirt crop, other-game supervised pair metric', 'limits':'Other-game labeled crop pretraining; target initial crops are unlabeled. Dev GT only determines arbitrary group mapping and threshold; target held-out segment not used in training or threshold choice. Same target match; repeated frames correlated; small sample; unmatched detection is not necessarily false positive; role/GK unknown.'},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
