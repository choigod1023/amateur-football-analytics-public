"""Compare full tiled detection with local re-detection on actual missed frames."""
import argparse,json,sys,time
from pathlib import Path
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.local_redetect import redetect
from app.low_confidence_recovery import iou
from ultralytics import YOLO
from track_review_clip import detect


def main():
    p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('probes',type=Path);p.add_argument('weights');p.add_argument('output',type=Path);a=p.parse_args()
    a.output.mkdir(exist_ok=True);model=YOLO(a.weights);cap=cv2.VideoCapture(a.video);out=[]
    for index,probe in enumerate(json.loads(a.probes.read_text(encoding='utf-8'))['probes']):
        cap.set(cv2.CAP_PROP_POS_MSEC,probe['time']*1000);ok,frame=cap.read()
        if not ok:raise RuntimeError('Frame decode failed')
        started=time.perf_counter();normal=detect(model,frame,'cam3',0,.1);base_ms=(time.perf_counter()-started)*1000
        started=time.perf_counter();local=redetect(model,frame,probe['before_box']);local_ms=(time.perf_counter()-started)*1000
        # Future box is evaluation guidance only, not input to the detector.
        hint=probe['roi_hint'];best=lambda boxes:float(max([iou(b,hint) for b in boxes],default=0))
        out.append({**probe,**local,'tiled_near_hint_iou':best(normal),'local_near_hint_iou':best(local['candidates']),
                    'tiled_ms':base_ms,'local_ms':local_ms,'label':'unverified_temporal_search_hint_not_ground_truth'})
        x1,y1,x2,y2=local['region'];image=frame.copy()
        for box in local['candidates']:
            bx1,by1,bx2,by2=map(int,box[:4]);cv2.rectangle(image,(bx1,by1),(bx2,by2),(0,255,255),1)
        crop=image[y1:y2,x1:x2];cv2.imwrite(str(a.output/f'probe-{index}.jpg'),cv2.resize(crop,(640,640)))
    cap.release()
    with (a.output/'results.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps([{'id':r['id'],'time':r['time'],'tiled_iou':r['tiled_near_hint_iou'],'local_iou':r['local_near_hint_iou'],'local_ms':r['local_ms']} for r in out]))


if __name__=='__main__':main()
