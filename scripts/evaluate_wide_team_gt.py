"""Local-only team grouping audit on labelled SoccerTrack boxes; not tracking evaluation."""
import argparse, collections, csv, json, sys
from pathlib import Path
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.team_suggestions import TeamSuggestions, shirt_histogram

def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        r=csv.reader(f); teams=next(r); ids=next(r); fields=next(r); next(r)
        data={int(x[0]): x for x in r if x and x[0]}
    return teams,ids,fields,data

def scan(folder, name, indices):
    teams,ids,fields,data=rows(folder/(name+'.csv')); cap=cv2.VideoCapture(str(folder/(name+'.mp4')))
    try:
        for n in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES,n-1); ok,frame=cap.read()
            if not ok or n not in data: raise ValueError(f'frame missing {name}:{n}')
            row=data[n]; tracks=[]; truth={}
            for i in range(1,len(fields),4):
                if i+3>=len(row) or teams[i] not in ('0','1') or ids[i]=='0' or not row[i+3]: continue
                try:x,y,w,h=map(float,row[i:i+4])
                except ValueError:continue
                if w<=0 or h<=0 or x<0 or y<0 or x+w>frame.shape[1] or y+h>frame.shape[0]:continue
                identity=f'{teams[i]}_{ids[i]}'; tracks.append(([x,y,x+w,y+h],identity));truth[identity]=int(teams[i])
            yield frame,tracks,truth
    finally: cap.release()

def main():
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--bootstrap-stride',type=int,default=1);args=p.parse_args()
    if not 1 <= args.bootstrap_stride <= 80: raise ValueError('invalid bootstrap stride')
    model=TeamSuggestions();init=[]
    for frame,tracks,truth in scan(args.folder,'0000_0030',(1 + i*args.bootstrap_stride for i in range(10))):
        model.update(frame,tracks)
        init.append((tracks,truth,frame))
    if model.centres is None: raise ValueError('no initial clusters')
    votes=collections.Counter()
    for tracks,truth,frame in init:
        for box,tid in tracks:
            group=model._classify(shirt_histogram(frame,box))
            if group is not None:votes[group,truth[tid]]+=1
    direct=votes[0,0]+votes[1,1];flip=votes[0,1]+votes[1,0]
    if direct==flip: raise ValueError('ambiguous reference mapping')
    mapping=0 if direct>flip else 1
    counts=collections.Counter();players=collections.defaultdict(collections.Counter)
    for frame,tracks,truth in scan(args.folder,'0120_0150',range(1,727,25)):
        groups=model.update(frame,tracks)
        for box,tid in tracks:
            pred=groups.get(tid); outcome='unknown' if pred is None else ('correct' if pred^mapping==truth[tid] else 'wrong')
            counts[outcome]+=1; players[tid][outcome]+=1
    print(json.dumps({'bootstrap_frames':10,'bootstrap_stride':args.bootstrap_stride,'test_frames':len(range(1,727,25)),'bootstrap_votes':dict((str(k),v) for k,v in votes.items()),'mapping':mapping,'counts':dict(counts),'players':{k:dict(v) for k,v in players.items()},'limitations':'Ground-truth boxes and stable GT identities; same game and camera; team-to-group mapping uses 10 labelled bootstrap frames; correlated samples, no referee or goalkeeper role evaluation.'},indent=2))
if __name__=='__main__':main()
