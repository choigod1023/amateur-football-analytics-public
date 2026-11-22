"""Compare real-video colour candidates with bounded same-ID history.

Ground truth is used only to align the two cluster labels once at the start,
and to score held-out frames; candidate formation uses no team labels.
"""
import argparse, collections, json, sys
from pathlib import Path
import torch
from ultralytics import YOLO
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.candidate_continuity import CandidateContinuity
from app.team_suggestions import TeamSuggestions, shirt_histogram
from app.tiled_tracking import TiledPlayerTracker
from scripts.evaluate_wide_team_gt import scan
from scripts.evaluate_wide_team_detected import match


def run(folder, weights, segment, start, length, device):
    torch.set_num_threads(2)
    model=YOLO(str(weights)); tracker=TiledPlayerTracker(model,device,640,.35)
    group=TeamSuggestions(); bootstrap=[]
    for frame,gt,truth in scan(folder,'0000_0030',range(1,11)):
        tracks=tracker.update(frame);group.update(frame,tracks);matched,_=match(tracks,gt,truth)
        bootstrap.extend((shirt_histogram(frame,box),matched[i]) for i,(box,tid) in enumerate(tracks) if i in matched)
    if group.centres is None: raise ValueError('Could not initialize color groups')
    votes=collections.Counter()
    for feat,truth in bootstrap:
        assigned=group._classify(feat)
        if assigned is not None:votes[assigned,truth]+=1
    direct=votes[0,0]+votes[1,1];flip=votes[0,1]+votes[1,0]
    if direct==flip:raise ValueError('Initial truth cannot map group labels')
    permutation=0 if direct>flip else 1
    tracker=TiledPlayerTracker(model,device,640,.35);history=CandidateContinuity(); restricted=CandidateContinuity()
    result={'baseline':collections.Counter(),'continuity':collections.Counter(),'only_missing_crop':collections.Counter()}
    for n,(frame,gt,truth) in enumerate(scan(folder,segment,range(start,start+length))):
        tracks=tracker.update(frame);matched,missing=match(tracks,gt,truth)
        raw=group.update(frame,tracks)
        smooth=history.update(raw, timestamp=n/25)
        # Preserve through a missing/too-small crop only; do not override a
        # real conflicting or out-of-distribution appearance observation.
        missing_crop={str(tid) for box,tid in tracks if shirt_histogram(frame,box) is None}
        guarded=restricted.update(raw, timestamp=n/25, holdable=missing_crop)
        for name,candidates in [('baseline',raw),('continuity',smooth),('only_missing_crop',guarded)]:
            c=result[name];c['gt_unmatched']+=missing
            for i,(_,tid) in enumerate(tracks):
                candidate=candidates.get(str(tid));team=matched.get(i)
                if team is None:
                    c['unmatched_detection']+=1;c['unmatched_assigned']+=int(candidate is not None)
                else:
                    c['matched']+=1
                    c['unknown' if candidate is None else ('correct' if candidate^permutation==team else 'wrong')]+=1
    return {'segment':segment,'start_frame':start,'frames_requested':length,
            'bootstrap_votes':{str(k):v for k,v in votes.items()},
            'results':{key:dict(value) for key,value in result.items()},
            'limitations':'Single game/camera; dependent frames and reused footage; bootstrap team labels only map cluster numbers for evaluation; unmatched detections may be unlabeled persons; roles not established.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path);p.add_argument('weights',type=Path);p.add_argument('--segment',default='0060_0090');p.add_argument('--start',type=int,default=101);p.add_argument('--frames',type=int,default=80);p.add_argument('--device',default='cpu')
    a=p.parse_args();print(json.dumps(run(a.folder,a.weights,a.segment,a.start,a.frames,a.device),ensure_ascii=False,indent=2))
