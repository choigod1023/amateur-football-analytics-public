"""Measure matched GT by pixel height and detector score on identical frames.

Detection only (no tracking); one low-threshold inference is reused to compare
thresholds. Dataset, model and results remain on the local machine.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import cv2
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.tiled_tracking import merge_boxes, tile_windows
from scripts.evaluate_wide_tracking import load_labels, match


def size_bin(box):
    height = box[3] - box[1]
    return 'under_40px' if height < 40 else ('40_to_79px' if height < 80 else '80px_plus')


def score_frame(targets, merged, threshold):
    predictions = [(b[:4], str(i)) for i, b in enumerate(merged) if b[4] >= threshold]
    matched = {x[0] for x in match(targets, predictions)}
    groups = {}
    for identity, box in targets:
        group = groups.setdefault(size_bin(box), {'gt': 0, 'matched': 0})
        group['gt'] += 1
        group['matched'] += int(identity in matched)
    return {'predicted': len(predictions), 'matched': len(matched), 'groups': groups}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('video', 'labels', 'weights', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--start', type=int, default=350)
    parser.add_argument('--frames', type=int, default=40)
    parser.add_argument('--stride', type=int, default=4)
    parser.add_argument('--overlap', type=float, default=.2)
    parser.add_argument('--device', default='0')
    args = parser.parse_args()
    thresholds = [.2, .5, .8, .95]
    totals = {str(x): {'predicted': 0, 'matched': 0, 'groups': {}} for x in thresholds}
    labels = load_labels(args.labels)
    cap = cv2.VideoCapture(str(args.video))
    model = YOLO(str(args.weights))
    frames = 0
    begun = time.perf_counter()
    try:
        for frame_no in range(args.start, args.start + args.frames * args.stride, args.stride):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ok, frame = cap.read()
            if not ok or frame_no not in labels:
                raise RuntimeError(f'Cannot read labeled frame {frame_no}')
            h, w = frame.shape[:2]
            boxes = []
            for left, right in tile_windows(w, h, overlap=args.overlap):
                result = model.predict(frame[:, left:right], device=args.device, imgsz=640, conf=.1,
                                       classes=[0], max_det=100, verbose=False)[0]
                if result.boxes is not None:
                    for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                        x1, y1, x2, y2 = map(float, box)
                        boxes.append([x1 + left, y1, x2 + left, y2, float(score)])
            merged = merge_boxes(boxes, w, h)
            for threshold in thresholds:
                score = score_frame(labels[frame_no], merged, threshold)
                total = totals[str(threshold)]
                total['predicted'] += score['predicted']
                total['matched'] += score['matched']
                for group, counts in score['groups'].items():
                    bucket = total['groups'].setdefault(group, {'gt': 0, 'matched': 0})
                    for k in ('gt', 'matched'):
                        bucket[k] += counts[k]
            frames += 1
    finally:
        cap.release()
    report = {'frames': frames, 'start': args.start, 'stride': args.stride,
              'inference_conf': .1, 'imgsz': 640, 'overlap': args.overlap,
              'elapsed_s': round(time.perf_counter()-begun, 2),
              'thresholds': totals,
              'limitations': 'Detection only; greedy IoU 0.5 matching; unmatched predictions may include officials or missing labels; repeated frames from one previously used match; not independent deployment accuracy.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
