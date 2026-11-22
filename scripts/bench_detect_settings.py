"""Does a different tile size, zoom (imgsz) or tile overlap of the person detector find more of the boxes a human confirmed? (research benchmark, read only, no training)

python scripts/bench_detect_settings.py <review store> <video> <weights> [--confidence 0.25] [--output result.json]

Same test boxes as scripts/bench_human_boxes.py (116 boxes the user drew or judged "a person") and scripts/bench_false_boxes.py (38 boxes judged "not a person").
Each setting is (tile px, imgsz, overlap of neighbouring tiles). The first one is the live setting (384, 768, 0.25); the script checks that its own tiler gives the same detections as
track_review_clip.detect before any other number is trusted. Printed per setting: human boxes found (all, the 7 unbiased evaluation-scene boxes of the user, boxes with a height under 20 px),
not-a-person boxes still reported, detections per frame, seconds per frame. Only the setting changes, so the model and the labels are never mixed with a training set.
"""
import argparse, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from bench_human_boxes import build_cases, WORK  # noqa: E402
from build_pseudo_tiles import iou  # noqa: E402

SETTINGS = [(384, 768, 0.25), (384, 1024, 0.25), (384, 1280, 0.25), (320, 960, 0.25), (256, 768, 0.25), (256, 1024, 0.25), (384, 768, 0.5), (512, 1024, 0.25)]


def detect(model, image, camera, confidence, tile, imgsz, overlap):
    height, width = image.shape[:2]
    top = int(height * tracker.PITCH_TOP[camera])
    found = []
    for y in [top + v for v in tracker.starts(height - top, tile, overlap)]:
        for x in tracker.starts(width, tile, overlap):
            result = model.predict(image[y:y + tile, x:x + tile], device=0, imgsz=imgsz, conf=confidence, classes=[0], max_det=100, verbose=False)[0]
            if result.boxes is None:
                continue
            for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                found.append([box[0] + x, box[1] + y, box[2] + x, box[3] + y, float(score)])
    found.sort(key=lambda d: -d[4])
    kept = []
    for d in found:
        if all(tracker.overlap_share(d, k) <= 0.6 for k in kept):
            kept.append(d)
    return kept


def false_cases(video):
    rows = []
    for name in ('person-check1-answers.json', 'person-check2-answers.json'):
        rows += json.loads((WORK / name).read_text(encoding='utf-8'))
    by_time = {}
    for r in rows:
        if r['label'] == 'wrong':
            by_time.setdefault(r['time'], []).append(r)
    cap = cv2.VideoCapture(video)
    out = []
    for t, items in by_time.items():
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, image = cap.read()
        if ok:
            out.append((image, items[0]['camera'] if items[0]['camera'] in tracker.PITCH_TOP else 'cam3', [r['box'] for r in items]))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('store'); p.add_argument('video'); p.add_argument('weights'); p.add_argument('--confidence', type=float, default=0.25); p.add_argument('--output', type=Path)
    args = p.parse_args()
    from ultralytics import YOLO
    model = YOLO(args.weights)
    cases, wrong = build_cases(args.store, args.video), false_cases(args.video)
    total = sum(len(c['boxes']) for c in cases)
    print(f'{len(cases)} frames, {total} human boxes, {sum(len(b) for _, _, b in wrong)} not-a-person boxes')
    check = cases[0]
    same = sorted(map(tuple, (map(lambda v: round(v, 1), d) for d in tracker.detect(model, check['image'], check['camera'], 0, args.confidence)))) == \
        sorted(map(tuple, (map(lambda v: round(v, 1), d) for d in detect(model, check['image'], check['camera'], args.confidence, 384, 768, 0.25))))
    print('own tiler equals track_review_clip.detect on the first frame:', same)
    if not same:
        raise SystemExit('the own tiler differs from the live detector; stopping')
    result = {}
    for tile, imgsz, overlap in SETTINGS:
        found = {'all': 0, 'eval': 0, 'small': 0}; counts = {'all': 0, 'eval': 0, 'small': 0}; detections = 0; started = time.time()
        for c in cases:
            dets = detect(model, c['image'], c['camera'], args.confidence, tile, imgsz, overlap)
            detections += len(dets)
            for box in c['boxes']:
                hit = any(iou(box, d) >= 0.3 for d in dets)
                keys = ['all'] + (['eval'] if c['group'] == 'drawn/eval' else []) + (['small'] if box[3] - box[1] < 20 else [])
                for key in keys:
                    found[key] += hit; counts[key] += 1
        seconds = (time.time() - started) / len(cases)
        reported = 0
        for image, camera, boxes in wrong:
            dets = detect(model, image, camera, args.confidence, tile, imgsz, overlap)
            reported += sum(any(iou(b, d) >= 0.3 for d in dets) for b in boxes)
        name = f'tile{tile}_imgsz{imgsz}_overlap{overlap}'
        result[name] = {'found': found, 'of': counts, 'not_a_person_reported': reported, 'detections_per_frame': round(detections / len(cases), 1), 'seconds_per_frame': round(seconds, 2)}
        print(f"{name:28s} found {found['all']}/{counts['all']} eval {found['eval']}/{counts['eval']} small(<20px) {found['small']}/{counts['small']} wrong-reported {reported} det/frame {detections / len(cases):.1f} {seconds:.2f}s/frame", flush=True)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
