"""How many of the boxes a human judged 'not a person' does a detector still report? (research benchmark, read only)

python scripts/bench_false_boxes.py <video> <confidence> <weights> [<weights> ...]

Boxes: label 'wrong' in work/person-check*-answers.json (one detector reported a person there, the user said no). A box counts as reported when a detection overlaps it with IoU >= 0.3.
Also prints the average number of detections per frame on the frames of these boxes, to see whether a model only gained by reporting more of everything.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from build_pseudo_tiles import iou  # noqa: E402

WORK = ROOT.parents[1] / 'work'


def main():
    video, conf, weights = sys.argv[1], float(sys.argv[2]), sys.argv[3:]
    rows = []
    for name in ('person-check1-answers.json', 'person-check2-answers.json'):
        rows += json.loads((WORK / name).read_text(encoding='utf-8'))
    wrong = [r for r in rows if r['label'] == 'wrong']
    by_time = {}
    for r in wrong:
        by_time.setdefault(r['time'], []).append(r)
    cap = cv2.VideoCapture(video)
    frames = {}
    for t in by_time:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, image = cap.read()
        if ok:
            frames[t] = image
    from ultralytics import YOLO
    for w in weights:
        model = YOLO(w)
        reported = total = detections = 0
        for t, image in frames.items():
            camera = by_time[t][0]['camera']
            dets = tracker.detect(model, image, camera, 0, conf)
            detections += len(dets)
            for r in by_time[t]:
                total += 1
                reported += any(iou(r['box'], d) >= 0.3 for d in dets)
        print(f'{Path(w).parent.name + "/" + Path(w).name:40s} conf {conf}: not-a-person boxes still reported {reported}/{total}, detections per frame {detections / len(frames):.1f}')


if __name__ == '__main__':
    main()
