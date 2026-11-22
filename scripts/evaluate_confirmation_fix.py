"""Paired tracker replay using shared real detector outputs; never train on GT."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ultralytics import YOLO
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import IterableSimpleNamespace
from evaluate_wide_tracking import match
from evaluate_identity_retraining import score_frame

WINDOWS = [(0, 30), (300, 330), (600, 630)]


def config():
    return IterableSimpleNamespace(track_high_thresh=.12, new_track_thresh=.12,
        track_low_thresh=.06, track_buffer=50, match_thresh=.98, fuse_score=True)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def truth(rows):
    return [(str(r['id']), [r['tag'][0], r['tag'][1], r['tag'][0]+r['tag'][2], r['tag'][1]+r['tag'][3]])
            for r in rows if r['tag'][2]>0 and r['tag'][3]>0 and not r.get('jump', False)]


def duplicate_pairs(tracks):
    # High-overlap output diagnostic, not a human-confirmed duplicate verdict.
    count=0
    for i, row in enumerate(tracks):
        for other in tracks[i+1:]:
            count += len(match([('one', row[:4])], [(other[:4], 'other')], .8))
    return count


def generate(root, out):
    model=YOLO(str(root/'outputs/football-coach-server/yolo11n.pt'))
    for group, name in [('305','video-02.mp4'), ('306','video-04.mp4')]:
        cache=out/f'detections-{group}.jsonl'
        if cache.exists():
            raise ValueError('Refusing to overwrite shared inference cache')
        video=root/'work/aihub-coaching-eval'/name
        labels=root/f'work/aihub-role-study/final-{group}-track.json'
        annotation={int(r['frame']):r['data'] for r in json.loads(labels.read_text(encoding='utf-8'))['tag']}
        cap=cv2.VideoCapture(str(video)); started=time.perf_counter(); frames=0
        with cache.open('w', encoding='utf-8') as handle:
            for window,(start,end) in enumerate(WINDOWS):
                cap.set(cv2.CAP_PROP_POS_FRAMES,start*30)
                for index in range(start*30,end*30):
                    ok,frame=cap.read()
                    if not ok: raise ValueError('Decode failed')
                    if index%6: continue
                    if index not in annotation: raise ValueError('GT frame missing')
                    prediction=model.predict(frame,device=0,imgsz=1280,conf=.1,classes=[0],max_det=150,verbose=False)[0]
                    array=prediction.boxes.data.cpu().numpy() if prediction.boxes is not None else np.zeros((0,6),np.float32)
                    handle.write(json.dumps({'frame':index,'window':window,'shape':frame.shape[:2],
                        'detections':array.tolist(),'targets':truth(annotation[index])})+'\n')
                    frames+=1
        cap.release()
        metadata={'video_sha256':sha(video),'labels_sha256':sha(labels),'weights_sha256':sha(root/'outputs/football-coach-server/yolo11n.pt'),
                  'cache_sha256':sha(cache),'frames':frames,'windows':WINDOWS,'analysis_fps':5,'imgsz':1280,'confidence':.1,
                  'decode_and_detection_wall_s':time.perf_counter()-started}
        (out/f'source-{group}.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        print(json.dumps({'generated':group,**metadata}),flush=True)


def replay(rows, tracker_class):
    total={k:0 for k in ('id_switches','matched','missed_gt','unmatched_detection','return_same','return_switched')}
    extra={k:0 for k in ('tracked','unconfirmed','overlap_pairs_08','consecutive_comparisons','consecutive_switches','identity_comparisons','identity_wrong','duplicate_gt_claims')}
    window=None; traces=[]; started=time.perf_counter()
    for row in rows:
        if row['window'] != window:
            tracker=tracker_class(config()); memory={}; previous={}; track_memory={}; window=row['window']; step=0
        array=np.asarray(row['detections'],np.float32).reshape(-1,6)
        tracks=tracker.update(Boxes(array,tuple(row['shape'])),None)
        targets=row.get('targets',[])
        matches=match(targets,[(r[:4],str(int(r[4]))) for r in tracks])
        ids=[str(int(r[4])) for r in tracks]
        score_frame({'targets':targets,'matches':matches,'raw_ids':ids,'step':step},{v:v for v in ids},memory,total)
        current=dict(matches); common=previous.keys() & current.keys()
        extra['consecutive_comparisons']+=len(common)
        extra['consecutive_switches']+=sum(previous[k]!=current[k] for k in common)
        for gt,tid in matches:
            if tid in track_memory:
                extra['identity_comparisons']+=1
                extra['identity_wrong']+=track_memory[tid]!=gt
            track_memory[tid]=gt
        # Counts additional outputs overlapping an already claimed GT at >=.5.
        all_claims=[match(targets,[(r[:4],str(int(r[4])))]) for r in tracks]
        claimed=[m[0][0] for m in all_claims if m]
        extra['duplicate_gt_claims']+=len(claimed)-len(set(claimed))
        extra['tracked']+=len(tracks)
        extra['unconfirmed']+=sum(not t.is_activated for t in tracker.tracked_stracks)
        extra['overlap_pairs_08']+=duplicate_pairs(tracks)
        traces.append({'frame':row['frame'],'window':window,'matches':matches,'tracked':len(tracks),'ids':ids,
                       'tracks':np.asarray(tracks).tolist()})
        previous=current;step+=1
    return {**total,**extra,'tracker_and_score_wall_s':time.perf_counter()-started},traces


def paired_output_changes(rows, baseline, candidate):
    result={k:0 for k in ('added_outputs','added_gt_matched','added_gt_unmatched','removed_outputs',
                          'removed_gt_matched','removed_gt_unmatched','shared_consecutive_comparisons',
                          'baseline_shared_switches','candidate_shared_switches')}
    previous_old={};previous_new={};window=None
    for row,old,new in zip(rows,baseline,candidate):
        if row.get('window')!=window:
            previous_old={};previous_new={};window=row.get('window')
        current_old=dict(old['matches']);current_new=dict(new['matches'])
        common=previous_old.keys() & previous_new.keys() & current_old.keys() & current_new.keys()
        result['shared_consecutive_comparisons']+=len(common)
        result['baseline_shared_switches']+=sum(previous_old[k]!=current_old[k] for k in common)
        result['candidate_shared_switches']+=sum(previous_new[k]!=current_new[k] for k in common)
        previous_old=current_old;previous_new=current_new
        old_by_detection={int(t[7]):t for t in old['tracks']}
        new_by_detection={int(t[7]):t for t in new['tracks']}
        for kind,source,indices,traces in (
                ('added',new_by_detection,new_by_detection.keys()-old_by_detection.keys(),new),
                ('removed',old_by_detection,old_by_detection.keys()-new_by_detection.keys(),old)):
            matched_ids={tid for _,tid in traces['matches']}
            for index in indices:
                result[kind+'_outputs']+=1
                suffix='matched' if str(int(source[index][4])) in matched_ids else 'unmatched'
                result[kind+'_gt_'+suffix]+=1
    if not any('targets' in r for r in rows):
        for key in result:
            if '_gt_' in key or 'shared_' in key:result[key]=None
    return result


def evaluate(root,out,candidate='confirmation'):
    from app.confirmation_tracker import ConfirmingBYTETracker
    from app.active_priority_tracker import ActivePriorityBYTETracker
    candidate_class={'confirmation':ConfirmingBYTETracker,'active-priority':ActivePriorityBYTETracker}[candidate]
    results={}
    for group in ('305','306','own'):
        if group=='own':
            path=root/'work/dropout-review-20261114/replay/observations.jsonl'
            original=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            rows=[{'frame':round(r['time']*30),'window':0,'shape':[1080,1920],'detections':r['tracking_detections']} for r in original]
        else:
            cache=out/f'detections-{group}.jsonl'
            source=json.loads((out/f'source-{group}.json').read_text(encoding='utf-8'))
            if sha(cache)!=source['cache_sha256']:
                raise ValueError('Shared detection cache hash mismatch')
            rows=[json.loads(line) for line in cache.read_text().splitlines()]
        results[group]={}
        mode_traces={}
        for mode,cls in [('baseline',BYTETracker),('candidate',candidate_class)]:
            result,traces=replay(rows,cls)
            if group=='own':
                for key in ('id_switches','matched','missed_gt','unmatched_detection','return_same','return_switched',
                            'consecutive_comparisons','consecutive_switches','identity_comparisons','identity_wrong','duplicate_gt_claims'):
                    result[key]=None
            results[group][mode]=result
            mode_traces[mode]=traces
            (out/f'trace-{group}-{mode}.json').write_text(json.dumps(traces),encoding='utf-8')
        results[group]['paired_output_changes']=paired_output_changes(rows,mode_traces['baseline'],mode_traces['candidate'])
        if group=='own':
            results[group]['limits']='No dense identity GT: counts and overlaps cannot establish correct identity or false-positive rates.'
        print(json.dumps({group:results[group]}),flush=True)
    results['limits']=['Same real detections in both arms; GT used only for scoring.',
        'Greedy IoU>=.5 diagnostic, not official HOTA/IDF1.',
        'Unmatched output is not a confirmed false positive; annotation gaps remain possible.',
        'These development videos were inspected previously; not an untouched final test.',
        'No GT identity for own recording; its output-count increase is not accuracy evidence.']
    results['candidate']=candidate
    source='confirmation_tracker.py' if candidate=='confirmation' else 'active_priority_tracker.py'
    results['candidate_source_sha256']=sha(Path(__file__).resolve().parents[1]/'app'/source)
    from app.evaluation_gate import tracking_gate
    results['validation_gate'] = tracking_gate(results, independent=False, own_identity_verified=False)
    (out/'comparison.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--generate-only',action='store_true');parser.add_argument('--evaluate-only',action='store_true')
    parser.add_argument('--candidate',choices=['confirmation','active-priority'],default='confirmation')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if not args.evaluate_only:generate(args.root,args.output)
    if not args.generate_only:evaluate(args.root,args.output,args.candidate)


if __name__=='__main__':main()
