"""Real person detections and shirt groups, scored locally against CSV boxes."""
import argparse, collections, json, sys
from pathlib import Path
import numpy as np, torch
from ultralytics import YOLO
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.team_suggestions import TeamSuggestions, shirt_histogram
from app.tiled_tracking import TiledPlayerTracker
from scripts.evaluate_wide_team_gt import scan

def iou(a,b):
    l=max(a[0],b[0]);t=max(a[1],b[1]);r=min(a[2],b[2]);bot=min(a[3],b[3]);inter=max(0,r-l)*max(0,bot-t)
    return inter/max(1e-9,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter)

def match(tracks,gt,truth):
    pairs=sorted(((iou(a,b),i,j) for i,(a,_) in enumerate(tracks) for j,(b,_) in enumerate(gt)),reverse=True)
    seen_i=set();seen_j=set();mapping={}
    for score,i,j in pairs:
        if score < .5:break
        if i in seen_i or j in seen_j:continue
        seen_i.add(i);seen_j.add(j);mapping[i]=truth[gt[j][1]]
    return mapping,len(gt)-len(seen_j)

def main():
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('weights',type=Path);p.add_argument('--test-frames',type=int,default=30);a=p.parse_args()
    torch.set_num_threads(3);model=YOLO(str(a.weights));tracker=TiledPlayerTracker(model,'cpu',640,.35);group=TeamSuggestions();bootstrap=[]
    for frame,gt,truth in scan(a.folder,'0000_0030',range(1,11)):
        tracks=tracker.update(frame);group.update(frame,tracks);matched,_=match(tracks,gt,truth)
        bootstrap.extend((shirt_histogram(frame,box),matched[i]) for i,(box,tid) in enumerate(tracks) if i in matched)
    if group.centres is None:raise ValueError('no clusters after 10 bootstrap frames')
    votes=collections.Counter()
    for feat,truth in bootstrap:
        result=group._classify(feat)
        if result is not None:votes[result,truth]+=1
    direct=votes[0,0]+votes[1,1];flip=votes[0,1]+votes[1,0]
    if direct==flip:raise ValueError('ambiguous labelled group mapping')
    permutation=0 if direct>flip else 1
    tracker=TiledPlayerTracker(model,'cpu',640,.35)
    counts={str(gate):collections.Counter() for gate in (.2,.3,.4,.7,float('inf'))}
    for frame,gt,truth in scan(a.folder,'0120_0150',range(1,a.test_frames+1)):
        tracks=tracker.update(frame);matched,missing=match(tracks,gt,truth)
        for gate in (.2,.3,.4,.7,float('inf')):
            group.max_distance=gate;counter=counts[str(gate)];counter['gt_unmatched']+=missing
            for i,(box,tid) in enumerate(tracks):
                cluster=group._classify(shirt_histogram(frame,box));team=matched.get(i)
                if team is None:counter['unmatched_detection']+=1;counter['unmatched_assigned']+=int(cluster is not None)
                else:
                    counter['matched']+=1;counter['unknown' if cluster is None else ('correct' if cluster^permutation==team else 'wrong')]+=1
                    if cluster is not None: counter[f'group_{cluster}_team_{team}']+=1
    print(json.dumps({'bootstrap_frames':10,'test_frames':a.test_frames,'bootstrap_votes':dict((str(k),v) for k,v in votes.items()),'results':{k:dict(v) for k,v in counts.items()},'limitations':'Same match/camera; true bootstrap labels only used to evaluate group/team direction; real CPU YOLO+ByteTrack, ground-truth IoU matching, missing GT not necessarily false positive; repeat players correlated; no verified referee or goalkeeper roles.'},indent=2))
if __name__=='__main__':main()
