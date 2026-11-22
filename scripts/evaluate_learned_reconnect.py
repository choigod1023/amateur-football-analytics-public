"""Video-disjoint, real-detection reappearance evaluation. No synthetic dropout."""
import argparse,hashlib,json,sys,time
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.learned_reconnect import LearnedLinker,validate_eval_group
from evaluate_wide_tracking import match
from ultralytics import YOLO
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import IterableSimpleNamespace


def main():
    p=argparse.ArgumentParser();p.add_argument('video',type=Path);p.add_argument('labels',type=Path);p.add_argument('model',type=Path);p.add_argument('weights');p.add_argument('output',type=Path);p.add_argument('--group',required=True);a=p.parse_args()
    model=json.loads(a.model.read_text());
    validate_eval_group(model,a.group)
    a.output.mkdir(exist_ok=False)
    annotation=json.loads(a.labels.read_text(encoding='utf-8'));labels={int(r['frame']):r['data'] for r in annotation['tag']}
    detector=YOLO(a.weights);cap=cv2.VideoCapture(str(a.video));fps=cap.get(cv2.CAP_PROP_FPS)
    windows=[(0,30),(300,330),(600,630)]
    totals={mode:{'id_switches':0,'matched':0,'missed_gt':0,'unmatched_detection':0,'joins':0,'correct_joins':0,'wrong_joins':0,'unresolved_joins':0,'return_same':0,'return_switched':0} for mode in ('raw','geometry','learned')}
    traces=[];events=[];started=time.perf_counter()
    for start,end in windows:
        config=IterableSimpleNamespace(track_high_thresh=.12,new_track_thresh=.12,track_low_thresh=.06,track_buffer=50,match_thresh=.98,fuse_score=True)
        tracker=BYTETracker(config);linkers={'geometry':LearnedLinker(),'learned':LearnedLinker(model)}
        memories={mode:{} for mode in totals};last_gt={};processed=0
        cap.set(cv2.CAP_PROP_POS_FRAMES,round(start*fps))
        for index in range(round(start*fps),round(end*fps)):
            ok,frame=cap.read()
            if not ok:raise RuntimeError('Evaluation video ended')
            if (index-round(start*fps))%6:continue
            t=index/fps
            predictions=detector.predict(frame,device=0,imgsz=1280,conf=.1,classes=[0],max_det=150,verbose=False)[0]
            array=predictions.boxes.data.cpu().numpy() if predictions.boxes is not None else np.zeros((0,6),np.float32)
            tracks=tracker.update(Boxes(array,frame.shape[:2]),None)
            targets=[]
            for row in labels.get(index,[]):
                x,y,w,h=row['tag']
                if w>0 and h>0 and not row.get('jump',False):targets.append((str(row['id']),[x,y,x+w,y+h]))
            raw_matches=match(targets,[(r[:4],str(int(r[4]))) for r in tracks]);raw_to_gt={raw:gt for gt,raw in raw_matches}
            mappings={'raw':{str(int(r[4])):str(int(r[4])) for r in tracks}}
            for mode,linker in linkers.items():
                mappings[mode],joins=linker.update(t,frame,tracks)
                for event in joins:
                    old_gt=last_gt.get(event['previous_raw']);new_gt=raw_to_gt.get(event['raw'])
                    kind='unresolved_joins' if old_gt is None or new_gt is None else 'correct_joins' if old_gt==new_gt else 'wrong_joins'
                    totals[mode]['joins']+=1;totals[mode][kind]+=1
                    events.append({'mode':mode,**event,'old_gt':old_gt,'new_gt':new_gt,'classification':kind})
            visible={gt for gt,_ in targets}
            for mode,mapping in mappings.items():
                found={gt:mapping[raw] for gt,raw in raw_matches};memory=memories[mode]
                memory_keys=list(memory)
                for gt in memory_keys:
                    if gt not in visible:del memory[gt]
                for gt,identity in found.items():
                    old=memory.get(gt)
                    if old:
                        totals[mode]['id_switches']+=old['id']!=identity
                        if old['step']<processed-1:totals[mode]['return_same' if old['id']==identity else 'return_switched']+=1
                    memory[gt]={'id':identity,'step':processed}
                totals[mode]['matched']+=len(found);totals[mode]['missed_gt']+=len(targets)-len(found)
                totals[mode]['unmatched_detection']+=len(tracks)-len(found)
            last_gt.update(raw_to_gt)
            traces.append({'frame':index,'time':t,'gt_count':len(targets),'tracked':len(tracks),'matches':raw_matches,'aliases':mappings})
            processed+=1
    cap.release()
    result={'video_group':a.group,'train_groups':model['train_video_groups'],'windows':windows,'frames':len(traces),'seconds':90,
        'model_sha256':hashlib.sha256(a.model.read_bytes()).hexdigest(),'video_sha256':hashlib.sha256(a.video.read_bytes()).hexdigest(),
        'threshold_frozen':model['threshold'],'results':totals,'wall_s':time.perf_counter()-started,
        'limits':['Single different daytime match, previously used for role evaluation; not a night-match guarantee.',
                  'Diagnostic IoU>=0.5 greedy annotation matching; not official IDF1/HOTA.',
                  'Unmatched detections can include unannotated people; not all are confirmed false positives.',
                  'Ground truth is used only for scoring, never for model training, candidate association or threshold tuning.']}
    for name,value in [('comparison.json',result),('events.json',events),('trace.json',traces)]:
        (a.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
