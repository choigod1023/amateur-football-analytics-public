import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
import cv2
from app.training_labels import TrainingLabels
import track_review_clip as tracker
from ultralytics import YOLO
store = ROOT.parents[1] / 'work' / 'human-labels' / 'public-own-match-review-20261111'
tl = TrainingLabels(store)
def iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0: return 0.0
    i = w * h; return i / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - i)
scenes = []
for s in tl.scene_queue():
    labs = tl.scene_labels(s['token'])
    drawn = [l['bbox'] for l in labs if l['origin'] == 'human_drawn']
    if drawn:
        img = cv2.imread(str(store / 'pending' / (s['token'] + '.jpg')))
        allb = [l['bbox'] for l in labs]
        scenes.append((s, img, drawn, allb))
total = sum(len(d) for _, _, d, _ in scenes)
print(len(scenes), 'scenes', total, 'drawn boxes')
for w in sys.argv[2:]:
    model = YOLO(w)
    for conf in [float(c) for c in sys.argv[1].split(',')]:
        found = 0; det_n = 0; by = {}
        for s, img, drawn, allb in scenes:
            H, W = img.shape[:2]
            cam = s['camera'] or 'cam3'
            dets = tracker.detect(model, img, cam, 0, conf)
            det_n += len(dets)
            for b in drawn:
                t = [b[0]*W, b[1]*H, b[2]*W, b[3]*H]
                ok = any(iou(t, d) >= 0.3 for d in dets); found += ok; k = s['split']; by[k] = [by.get(k, [0, 0])[0] + ok, by.get(k, [0, 0])[1] + 1]
        print(f'{Path(w).name:16s} conf {conf}: found {found}/{total}, detections {det_n} {by}', flush=True)
