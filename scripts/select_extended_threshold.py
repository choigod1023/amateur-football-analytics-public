"""Select detection score using only the six independent AI Hub development frames."""
import argparse, json, sys
from pathlib import Path
import cv2
from ultralytics import YOLO
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.tiled_tracking import tile_windows, merge_boxes
from evaluate_wide_tracking import match

p = argparse.ArgumentParser()
p.add_argument('--dataset', type=Path, required=True)
p.add_argument('--weights', type=Path, required=True)
p.add_argument('--device', default='cpu')
a = p.parse_args()
model = YOLO(str(a.weights))
thresholds = [.25,.3,.35,.4,.45,.5,.55,.6,.65,.7,.75,.8,.85,.9,.95,.98]
totals = {t: [0,0,0] for t in thresholds}
for image in sorted((a.dataset/'images/val').glob('*.jpg')):
    frame=cv2.imread(str(image)); h,w=frame.shape[:2]
    truth=[]
    for i,line in enumerate((a.dataset/'labels/val'/f'{image.stem}.txt').read_text().splitlines()):
        _,x,y,bw,bh=map(float,line.split()); truth.append((str(i),[(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h]))
    detections=[]
    for left,right in tile_windows(w,h):
        boxes=model.predict(frame[:,left:right],device=a.device,imgsz=640,conf=.25,classes=[0],max_det=100,verbose=False)[0].boxes
        for box,score in zip(boxes.xyxy.cpu().numpy(),boxes.conf.cpu().numpy()):
            x1,y1,x2,y2=map(float,box); detections.append([x1+left,y1,x2+left,y2,float(score)])
    merged=merge_boxes(detections,w,h)
    for t in thresholds:
        selected=[(row[:4],str(i)) for i,row in enumerate(merged) if row[4]>=t]
        values=totals[t]; values[0]+=len(truth); values[1]+=len(selected); values[2]+=len(match(truth,selected))
results=[]
for t,(gt,pred,matched) in totals.items():
    results.append({'threshold':t,'gt':gt,'predicted':pred,'matched':matched,'f1':2*matched/(gt+pred) if gt+pred else 0})
print(json.dumps({'selected':max(results,key=lambda x:(x['f1'],x['threshold'])),'results':results,'note':'Development labels may omit people; greedy IoU .5, not a production accuracy estimate.'},indent=2))
