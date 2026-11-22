"""Compare full and tiled ball inference on an explicitly labelled image set."""
import argparse
import json
import time
from pathlib import Path

import cv2
from ultralytics import YOLO
from app.ball_detection import ball_class_id, tiled_ball_candidates
from app.main import ball_candidates_from_boxes


def iou(a, b):
    area = max(0., min(a[2], b[2])-max(a[0], b[0])) * max(0., min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - area
    return area / union if union else 0.


def evaluate(images, labels, weights, label_class, *, device='cpu', confidence=.15, image_size=640):
    files = sorted(images.glob('*.jpg'))
    if not files: raise ValueError('No JPG images')
    model = YOLO(str(weights))
    cls = ball_class_id(model.names)
    if cls is None: raise ValueError('Model needs exactly one ball or sports ball class')
    totals = {mode: {'images': 0, 'reference_boxes': 0, 'predicted_boxes': 0,
                     'matched_iou50': 0, 'elapsed_s': 0.} for mode in ('full', 'tiles')}
    for file in files:
        lab = labels / (file.stem + '.txt')
        if not lab.is_file(): raise ValueError(f'Missing label for {file.name}')
        frame = cv2.imread(str(file))
        if frame is None: raise ValueError(f'Cannot decode {file.name}')
        truth = []
        for line in lab.read_text(encoding='utf-8').splitlines():
            values = [float(v) for v in line.split()]
            if len(values) != 5: raise ValueError(f'Invalid label for {file.name}')
            c, x, y, w, h = values
            if c == label_class: truth.append([x-w/2, y-h/2, x+w/2, y+h/2])
        for mode, out in totals.items():
            started = time.perf_counter()
            if mode == 'tiles':
                candidates = tiled_ball_candidates(model, frame, class_id=cls, device=device, image_size=image_size, confidence=confidence)
            else:
                pred = model.predict(frame, classes=[cls], device=device, imgsz=image_size, conf=confidence, verbose=False)[0]
                candidates = ball_candidates_from_boxes(pred.boxes, frame.shape[1], frame.shape[0])
            out['elapsed_s'] += time.perf_counter() - started
            boxes = [item['bbox_image_norm'] for item in candidates]
            pairs = sorted(((iou(p, t), i, j) for i, p in enumerate(boxes) for j, t in enumerate(truth)), reverse=True)
            used_p, used_t = set(), set()
            for score, i, j in pairs:
                if score < .5: break
                if i not in used_p and j not in used_t: used_p.add(i); used_t.add(j)
            out['images'] += 1
            out['reference_boxes'] += len(truth)
            out['predicted_boxes'] += len(boxes)
            out['matched_iou50'] += len(used_p)
    for out in totals.values(): out['elapsed_s'] = round(out['elapsed_s'], 3)
    return {'model':str(weights), 'confidence':confidence, 'image_size':image_size, 'results':totals,
            'limitations':'JPG only; labels, match splits and model pretraining overlap require independent audit. Time includes inference and Python processing, not video decode, network, player tracking or UI.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images',type=Path,required=True);parser.add_argument('--labels',type=Path,required=True)
    parser.add_argument('--weights',type=Path,required=True);parser.add_argument('--label-class',type=int,default=0)
    parser.add_argument('--device',default='cpu');parser.add_argument('--confidence',type=float,default=.15)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.images,args.labels,args.weights,args.label_class,device=args.device,confidence=args.confidence),ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
