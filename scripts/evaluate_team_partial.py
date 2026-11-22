"""Compare team predictions against partial manually marked points.

No annotations or footage are shipped. Input points are not bounding boxes and
unmatched/ambiguous people are explicitly excluded from the classifier score.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
import sys

import cv2
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.guarded_team import classify_guarded
from app.main import classify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True, help='directory containing groundtruth-manual and muvy-samples')
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    samples = json.loads((args.work / 'groundtruth-manual/partial-reference.json').read_text(encoding='utf-8'))
    # Approximate observed colours, not independently measured references.
    palettes = {'05': {'home': [0, 35, 235], 'away': [80, 110, 100]},
                '07': {'home': [0, 35, 235], 'away': [120, 150, 80]}}
    model = YOLO(str(args.weights))
    report = []
    for sample in samples:
        event, frame = sample['event'], sample['frame']
        if event not in palettes:
            continue
        image = cv2.imread(str(args.work / f'muvy-samples/soccer_event_{event}/cam_01_S{event}/img/{frame}.jpg'))
        if image is None:
            raise FileNotFoundError(f'missing image {event}/{frame}')
        boxes = model.predict(image, device=args.device, imgsz=1280, conf=.35, classes=[0], verbose=False)[0].boxes.xyxy.cpu().numpy()
        points = [p for p in sample['points'] if p['role'] == 'player' and p['team'] in ('light', 'dark')]
        matches = []
        for point in points:
            x, y = point['xy']
            matches.append([i for i, (x1, y1, x2, y2) in enumerate(boxes) if x1 <= x <= x2 and y1 <= y <= y2])
        # A box covering two annotated people is also ambiguous, regardless of order.
        use_counts = Counter(i for ids in matches if len(ids) == 1 for i in ids)
        counts = Counter()
        for point, ids in zip(points, matches):
            if len(ids) != 1 or use_counts[ids[0]] != 1:
                counts['unmatched_or_ambiguous'] += 1
                continue
            truth = 'home' if point['team'] == 'light' else 'away'
            for name, fn in [('median', classify), ('guarded', classify_guarded)]:
                prediction = fn(image, boxes[ids[0]], palettes[event])
                outcome = 'correct' if prediction == truth else 'unknown' if prediction == 'unknown' else 'wrong'
                counts[f'{name}_{outcome}'] += 1
        report.append({'event': event, 'frame': frame, 'marked_players': len(points), 'detected_boxes': len(boxes), **counts})
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
