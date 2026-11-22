"""Compare person detectors on the photos the reviewer labelled completely (split "eval"), read only.

Usage: python scripts/evaluate_person_detector.py <review store> <confidence list, comma separated> <weights> [<weights> ...]

For every weights file and confidence it prints how many of the labelled people were found (a detection overlapping the
labelled box with IoU >= 0.3) and how many detections matched nobody per photo. Detection uses the same 384 px tiles as the
tracking script. Caution: most labelled boxes started as candidates of the small stock detector, so the stock model is
favoured by this test; it says little about people that every detector misses.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import track_review_clip as tracker  # noqa: E402

PEOPLE = ('player', 'goalkeeper', 'referee', 'spectator', 'unknown')


def iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def main():
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    import cv2
    from ultralytics import YOLO
    store = Path(sys.argv[1])
    confidences = [float(v) for v in sys.argv[2].split(',')]
    scenes = {}
    for path in store.glob('*.json'):
        try:
            label = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(label, dict) and (label.get('source_provenance') or {}).get('split') == 'eval' and label.get('role') in PEOPLE and 'bbox_image_norm' in label:
            scenes.setdefault(label['image'], []).append(label['bbox_image_norm'])
    images = {name: cv2.imread(str(store / name)) for name in scenes}
    people = sum(len(v) for v in scenes.values())
    print(f'{len(scenes)} completely labelled photos, {people} people')
    for weights in sys.argv[3:]:
        model = YOLO(weights)
        for conf in confidences:
            found = false_alarms = 0
            for name, boxes in scenes.items():
                image = images[name]
                height, width = image.shape[:2]
                truth = [[b[0] * width, b[1] * height, b[2] * width, b[3] * height] for b in boxes]
                detections = tracker.detect(model, image, 'cam3', 0, conf)
                found += sum(1 for t in truth if any(iou(t, d) >= 0.3 for d in detections))
                false_alarms += sum(1 for d in detections if not any(iou(t, d) >= 0.3 for t in truth))
            print(f'{Path(weights).name:22s} conf {conf:.2f}: found {found}/{people} ({100 * found / people:.0f}%), detections matching nobody per photo {false_alarms / len(scenes):.1f}')


if __name__ == '__main__':
    main()
