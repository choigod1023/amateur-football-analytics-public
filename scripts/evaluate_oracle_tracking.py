"""Diagnostic GT-box intervention, never a deployable detector accuracy claim.

Annotation identities are used ONLY by the scorer, not by BYTETracker. All modes
are scored on the same 5 Hz frames; the 15 Hz arm receives extra real GT boxes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.trackers.bot_sort import BOTSORT
from ultralytics.utils import IterableSimpleNamespace
from evaluate_wide_tracking import match
from evaluate_identity_retraining import score_frame
from app.observation_boxes import current_detection_boxes

WINDOWS = [(0,30),(300,330),(600,630)]
METRICS = ('id_switches','matched','missed_gt','unmatched_detection','return_same','return_switched')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def targets(rows):
    result=[]
    for row in rows:
        x,y,w,h=map(float,row['tag'])
        if not all(np.isfinite([x,y,w,h])):
            raise ValueError('Non-finite ground truth')
        if w>0 and h>0 and not row.get('jump',False):
            result.append((str(row['id']),[x,y,x+w,y+h]))
    if len({r[0] for r in result}) != len(result):
        raise ValueError('Duplicate annotation ID in one frame')
    return result


def oracle_detections(ground_truth):
    # No annotation ID or team/class metadata is given to the tracker.
    return np.asarray([[*box,1.,0.] for _,box in ground_truth],np.float32).reshape(-1,6)


def consecutive_identity_counts(previous, current):
    common = previous.keys() & current.keys()
    return len(common), sum(previous[k] != current[k] for k in common)


def run(labels,shape,update_fps,video=None):
    if update_fps not in (5,15):
        raise ValueError('Frozen experiment supports 5 or 15 Hz')
    total={k:0 for k in METRICS};updates=scored=0;traces=[]
    observed_total={k:0 for k in METRICS}
    consecutive={'comparisons':0,'switches':0}
    unconfirmed=0
    started=time.perf_counter()
    for start,end in WINDOWS:
        config=IterableSimpleNamespace(track_high_thresh=.12,new_track_thresh=.12,
            track_low_thresh=.06,track_buffer=50*(update_fps//5),match_thresh=.98,fuse_score=True)
        capture=None
        if video is not None:
            config.gmc_method='sparseOptFlow';config.proximity_thresh=.5
            config.appearance_thresh=.8;config.with_reid=False;config.model='auto'
            tracker=BOTSORT(config)
            capture=cv2.VideoCapture(str(video));capture.set(cv2.CAP_PROP_POS_FRAMES,start*30)
        else:
            tracker=BYTETracker(config)
        memory={};observed_memory={};previous={};step=0
        for index in range(start*30,end*30,30//update_fps):
            if index not in labels:
                raise ValueError('Missing annotation frame; interpolation is forbidden')
            truth=targets(labels[index])
            detections=oracle_detections(truth)
            image=None
            if capture is not None:
                ok,image=capture.read()
                if not ok:raise ValueError('Failed video decode')
                for _ in range(30//update_fps-1):capture.grab()
            tracks=tracker.update(Boxes(detections,shape),image)
            updates+=1
            if (index-start*30)%6:
                continue
            unconfirmed+=sum(not t.is_activated for t in tracker.tracked_stracks)
            matches=match(truth,[(r[:4],str(int(r[4]))) for r in tracks])
            raw=[str(int(r[4])) for r in tracks]
            score_frame(dict(targets=truth,matches=matches,raw_ids=raw,step=step),
                        {r:r for r in raw},memory,total)
            observed,diagnostics=current_detection_boxes(tracks,detections)
            if any(not d['accepted'] for d in diagnostics):
                raise ValueError('Invalid current detection assignment')
            # Scoring-only provenance: which GT input was assigned this track ID?
            observed_matches=[(truth[int(r[7])][0],str(int(r[4]))) for r in observed]
            observed_raw=[str(int(r[4])) for r in observed]
            score_frame(dict(targets=truth,matches=observed_matches,raw_ids=observed_raw,step=step),
                        {r:r for r in observed_raw},observed_memory,observed_total)
            current=dict(observed_matches)
            count,switches=consecutive_identity_counts(previous,current)
            consecutive['comparisons']+=count;consecutive['switches']+=switches
            previous=current
            traces.append({'frame':index,'matches':matches,'observed_matches':observed_matches,
                           'tracked':len(raw),'gt':len(truth)})
            step+=1;scored+=1
        if capture is not None:capture.release()
    return {'results':total,'unconfirmed_tracks_on_scored_frames':unconfirmed,'current_detection_results':observed_total,'consecutive_current_identity':consecutive,'tracking_updates':updates,'scored_frames':scored,
            'runtime_scope':('tracker, scorer, video decode and GMC; detector excluded' if video is not None else 'tracker and scorer; detector and video decode excluded'),
            'tracker_and_score_wall_s':time.perf_counter()-started,'traces':traces}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--botsort-gmc', action='store_true')
    for name in ('video','labels','baseline','output'):p.add_argument(name,type=Path)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    baseline=json.loads(args.baseline.read_text(encoding='utf-8'))
    if baseline['video_sha256']!=sha(args.video) or baseline['labels_sha256']!=sha(args.labels):
        raise ValueError('Baseline source mismatch')
    if baseline['windows']!=[list(w) for w in WINDOWS] or baseline['analysis_fps']!=5 or baseline['frames']!=450:
        raise ValueError('Baseline frame schedule mismatch')
    data=json.loads(args.labels.read_text(encoding='utf-8'))
    labels={int(r['frame']):r['data'] for r in data['tag']}
    if len(labels)!=len(data['tag']):raise ValueError('Duplicate frame annotations')
    capture=cv2.VideoCapture(str(args.video))
    fps=capture.get(cv2.CAP_PROP_FPS);ok,frame=capture.read();capture.release()
    if not ok or abs(fps-30)>.1:raise ValueError('Expected readable 30 Hz recording')
    result={'baseline':{k:baseline['results']['raw'][k] for k in METRICS},
            'baseline_file':str(args.baseline.resolve()),'baseline_sha256':sha(args.baseline),
            'video_sha256':sha(args.video),'labels_sha256':sha(args.labels),
            'windows':WINDOWS,'scored_fps':5,'oracle':{}}
    for rate in (5,15):
        arm=run(labels,frame.shape[:2],rate)
        (args.output/f'trace-{rate}.json').write_text(json.dumps(arm.pop('traces')),encoding='utf-8')
        result['oracle'][str(rate)]=arm
    if args.botsort_gmc:
        arm=run(labels,frame.shape[:2],15,args.video)
        (args.output/'trace-botsort-gmc-15.json').write_text(json.dumps(arm.pop('traces')),encoding='utf-8')
        result['oracle']['botsort_gmc_15']=arm
    result['limits']=['GT boxes with confidence 1 replace the detector, not a measured detector improvement.',
        'Input identities and teams are removed; identity GT is used only for scoring.',
        'Diagnostic greedy IoU>=0.5, not official HOTA/IDF1; annotations may have their own errors.',
        '15 Hz requires real dense annotations; no interpolation. Lost-track lifetime is preserved in seconds.',
        'Runtime always excludes detector; BoTSORT arm includes decode/GMC, BYTETracker arms exclude decode. Not end-to-end real-time performance.',
        'Measured baseline uses saved raw BYTETracker results from verified identical source and schedule.']
    (args.output/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
