"""Simulate detector dropouts on real wide-camera video (research only)."""
import argparse, json, math, statistics, sys, time
from pathlib import Path
import cv2, numpy as np
from ultralytics import YOLO
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.experimental_map import ExperimentalMap
from app.main import project
from app.tiled_tracking import TiledPlayerTracker
from scripts.evaluate_wide_tracking import load_labels, match


def evaluate(video, labels, weights, calibration, start=350, steps=40, stride=4, device='cuda:0'):
    cal={**calibration,'validated':True}  # local experiment only
    dims=cal['field_size_m']; gt=load_labels(labels)
    model=YOLO(str(weights)); tracker=TiledPlayerTracker(model,device,640,.35)
    memory=ExperimentalMap(); cap=cv2.VideoCapture(str(video))
    pred_errors=[]; hold_errors=[]; lost=0; missing_truth=0; previous_map={}; last_positions={}
    start_time=time.perf_counter()
    try:
        for i in range(steps):
            idx=start+i*stride
            if idx not in gt: break
            target={tid:box for tid,box in gt[idx]}
            now=i*stride/25.0
            if i%8 in (6,7):
                predictions=memory.update([],now,dims)
                for p in predictions:
                    label_id=previous_map.get(p['id']); box=target.get(label_id)
                    if box is None:
                        missing_truth+=1; continue
                    tx,ty=project(((box[0]+box[2])/2,box[3]),cal)
                    if tx is None or ty is None: continue
                    last=last_positions.get(p['id'])
                    if last is None: continue
                    pred_errors.append(math.hypot((p['x']-tx)*dims[0],(p['y']-ty)*dims[1]))
                    hold_errors.append(math.hypot((last[0]-tx)*dims[0],(last[1]-ty)*dims[1]))
                lost+=1
            else:
                cap.set(cv2.CAP_PROP_POS_FRAMES,idx); ok,frame=cap.read()
                if not ok: break
                tracks=tracker.update(frame)
                previous_map={pred_id:gt_id for gt_id,pred_id in match(gt[idx],tracks)}
                points=[]
                for box,tid in tracks:
                    x,y=project(((box[0]+box[2])/2,box[3]),cal)
                    if x is not None and y is not None:
                        points.append({'id':str(tid),'x':x,'y':y})
                memory.update(points,now,dims)
                last_positions={p['id']:(p['x'],p['y']) for p in points}
    finally: cap.release()
    return {'simulated_dropout_frames':lost,'matched_estimates':len(pred_errors),'unmatched_estimates':missing_truth,
        'prediction_median_m':statistics.median(pred_errors) if pred_errors else None,
        'prediction_p90_m':float(np.percentile(pred_errors,90)) if pred_errors else None,
        'last_position_median_m':statistics.median(hold_errors) if hold_errors else None,
        'last_position_p90_m':float(np.percentile(hold_errors,90)) if hold_errors else None,
        'wall_s':round(time.perf_counter()-start_time,2),
        'limitation':'Same camera; synthetic dropouts; matches held fixed from last frame; reference-projected annotated boxes are not independently measured positions.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('video','labels','weights','config'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--device',default='cuda:0');parser.add_argument('--start',type=int,default=350);parser.add_argument('--steps',type=int,default=40)
    a=parser.parse_args(); config=json.loads(a.config.read_text(encoding='utf-8-sig'))
    print(json.dumps(evaluate(a.video,a.labels,a.weights,config['calibration'],a.start,a.steps,device=a.device),ensure_ascii=False,indent=2))
