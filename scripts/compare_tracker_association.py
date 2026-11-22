"""Compare ByteTrack association on identical cached tiled detections.

Diagnostic only: unmatched predictions can be unlabeled people; ID gaps are
not standard HOTA/IDF1. Never train or select thresholds using this evaluation.
"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
from ultralytics import YOLO
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import YAML, IterableSimpleNamespace
from ultralytics.utils.checks import check_yaml
from app.tiled_tracking import merge_boxes, tile_windows
from scripts.evaluate_wide_tracking import load_labels, match, MissedReappearanceAudit


def run(video, labels, weights, device, start, frames, stride, confidence):
    gt = load_labels(labels)
    model = YOLO(str(weights))
    configs = [('baseline',30,0.8), ('short_buffer',5,0.8), ('long_buffer',90,0.8), ('stricter_match',30,0.6), ('looser_match',30,0.9)]
    experiments = {}
    for name, buffer, threshold in configs:
        cfg = IterableSimpleNamespace(**YAML.load(check_yaml('bytetrack.yaml')))
        cfg.track_buffer, cfg.match_thresh = buffer, threshold
        experiments[name] = {'tracker': BYTETracker(args=cfg), 'gap': MissedReappearanceAudit(), 'previous': {}, 'matched': 0, 'predicted': 0, 'gt': 0, 'id_changes': 0, 'track_people': {}, 'person_tracks': {}}
    cap = cv2.VideoCapture(str(video)); cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    processed = 0; begin = time.perf_counter()
    try:
        for idx in range(frames):
            number = start + idx * stride
            ok, frame = cap.read()
            if not ok or number not in gt: break
            height, width = frame.shape[:2]; found = []
            for left, right in tile_windows(width, height):
                result = model.predict(frame[:,left:right], device=device, imgsz=640, conf=confidence, classes=[0], max_det=100, verbose=False)[0]
                if result.boxes is not None:
                    for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                        x1,y1,x2,y2 = map(float,box)
                        found.append([x1+left,y1,x2+left,y2,float(score)])
            merged = merge_boxes(found,width,height)
            for data in experiments.values():
                tracks = data['tracker'].update(Boxes(merged.copy(), (height,width)), frame)
                predictions = [(row[:4],int(row[4])) for row in tracks]
                pairs = match(gt[number],predictions); now = dict(pairs)
                data['gap'].update(gt[number],pairs)
                for person, track in pairs:
                    data['track_people'].setdefault(track, set()).add(person)
                    data['person_tracks'].setdefault(person, set()).add(track)
                data['id_changes'] += sum(key in data['previous'] and data['previous'][key] != track for key,track in now.items())
                data['previous'] = now
                data['matched'] += len(pairs); data['predicted'] += len(predictions); data['gt'] += len(gt[number])
            processed += 1
            for _ in range(stride-1):
                if not cap.grab(): break
    finally:
        cap.release()
    result = {'frames':processed,'stride':stride,'confidence':confidence,'seconds':round(time.perf_counter()-begin,2),'experiments':{}}
    for name, d in experiments.items():
        result['experiments'][name] = {'matched':d['matched'], 'gt':d['gt'], 'predicted':d['predicted'], 'consecutive_id_changes':d['id_changes'], 'gap_reappearance':d['gap'].summary(), 'tracks_matched_multiple_people':sum(len(v)>1 for v in d['track_people'].values()), 'people_matched_multiple_tracks':sum(len(v)>1 for v in d['person_tracks'].values())}
    return result

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('video','labels','weights'): p.add_argument('--'+key,required=True,type=Path)
    p.add_argument('--device',default='cpu'); p.add_argument('--start',type=int,default=350); p.add_argument('--frames',type=int,default=100); p.add_argument('--stride',type=int,default=2); p.add_argument('--confidence',type=float,default=.95)
    a=p.parse_args(); print(json.dumps(run(a.video,a.labels,a.weights,a.device,a.start,a.frames,a.stride,a.confidence),indent=2))
