"""Pick the places where two person detectors disagree and put them on /alerts as the question 'is this a person?' (the store is only added to).

python scripts/build_person_check.py <store> <video> --session NAME --weights-a A.pt --weights-b B.pt [--count 60]

A spot is a box that one detector finds with a score of 0.25 to 0.6 and the other does not find. Answers: 맞음 = a person, 틀림 = not a person, 쓸모없음 = cannot tell.
The picture is a crop around the box, drawn larger, with the box in red.
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from app.camera_segments import camera_of  # noqa: E402
from build_pseudo_tiles import iou  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('video')
    parser.add_argument('--session', required=True)
    parser.add_argument('--weights-a', required=True)
    parser.add_argument('--weights-b', required=True)
    parser.add_argument('--count', type=int, default=60)
    parser.add_argument('--frames', type=int, default=150)
    parser.add_argument('--seed', type=int, default=7)
    args = parser.parse_args()
    if not re.match(r'^[A-Za-z0-9_-]{1,40}$', args.session):
        raise SystemExit('bad session name')
    folder = Path(args.store) / 'alerts' / args.session
    if (folder / 'alerts.jsonl').exists():
        raise SystemExit('session exists')
    from ultralytics import YOLO
    a, b = YOLO(args.weights_a), YOLO(args.weights_b)
    cap = cv2.VideoCapture(args.video)
    fps, total = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
    random.seed(args.seed)
    spots = []
    for i in range(args.frames):
        t = 70 + (total / fps - 70) * (i + random.random()) / args.frames
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, image = cap.read()
        if not ok:
            continue
        camera = camera_of(t)
        if camera is None:      # the cam2 part: no detector crop
            continue
        found_a, found_b = tracker.detect(a, image, camera, 0, 0.25), tracker.detect(b, image, camera, 0, 0.25)
        frame_spots = []
        for mine, other, name in ((found_a, found_b, 'A'), (found_b, found_a, 'B')):
            for d in mine:
                if d[4] < 0.6 and not any(iou(d, o) >= 0.3 for o in other):
                    frame_spots.append((abs(d[4] - 0.4), t, d, image, name))
        frame_spots.sort(key=lambda s: s[0])
        spots.extend(frame_spots[:2])
    spots.sort(key=lambda s: s[0])
    spots = spots[:args.count]
    spots.sort(key=lambda s: s[1])
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    meta = []
    for n, (_, t, d, image, name) in enumerate(spots):
        meta.append({'n': n, 'time': round(t, 1), 'box': [round(float(v), 1) for v in d[:4]], 'score': round(d[4], 3), 'found_by': name, 'camera': camera_of(t)})
        h, w = image.shape[:2]
        cx, cy = (d[0] + d[2]) / 2, (d[1] + d[3]) / 2
        half_w, half_h = 160, 110
        x0, y0 = int(min(max(0, cx - half_w), w - 2 * half_w)), int(min(max(0, cy - half_h), h - 2 * half_h))
        crop = image[y0:y0 + 2 * half_h, x0:x0 + 2 * half_w].copy()
        cv2.rectangle(crop, (int(d[0] - x0), int(d[1] - y0)), (int(d[2] - x0), int(d[3] - y0)), (0, 0, 255), 1)
        crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        cv2.imwrite(str(folder / f'alerts_{n:04d}.jpg'), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        rows.append({'time': round(t, 1), 'kind': 'person_check', 'polarity': 'neutral', 'title': '이 상자 안에 사람이 있나요?',
                     'text': '빨간 상자 안에 선수나 심판 같은 사람이 있으면 맞음, 사람이 아니면 틀림, 알 수 없으면 쓸모없음을 눌러 주세요.'})
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    (folder / 'spots.json').write_text(json.dumps(meta), encoding='utf-8')
    print(len(rows), 'spots ->', folder)


if __name__ == '__main__':
    main()
