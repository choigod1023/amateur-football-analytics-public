"""Union of two person detectors for the analysis after the match (research only, not used live).

Rule: every box of detector A (the match-trained small model) is kept; a box of detector B (the large model) is added when its score is at least
`B_ADD` and it overlaps no box of A with IoU >= 0.3. Reason: in the person-check answers the boxes that only the large model found were people in 60 of 68 cases.

python scripts/detect_union.py <review store> <video> <weights A> <weights B> [--frames 40]
Prints (a) the user's hand-drawn boxes found, (b) precision of the added boxes from the person-check answers, (c) detections per frame and seconds per frame.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from app.training_labels import TrainingLabels  # noqa: E402
from app.camera_segments import camera_of  # noqa: E402
from build_pseudo_tiles import iou  # noqa: E402

B_ADD = 0.35
B_CONFIDENCE = 0.25


def union(found_a, found_b, b_add=B_ADD, overlap=0.3):
    """found_*: [[x1, y1, x2, y2, score]]. Returns (all boxes, added boxes of B)."""
    added = [b for b in found_b if b[4] >= b_add and not any(iou(b, a) >= overlap for a in found_a)]
    return list(found_a) + added, added


def detect_union(model_a, model_b, image, camera, conf_a=0.25, device=0):
    found_a = tracker.detect(model_a, image, camera, device, conf_a)
    found_b = tracker.detect(model_b, image, camera, device, B_CONFIDENCE)
    return union(found_a, found_b)


def main():
    parser = argparse.ArgumentParser()
    for name in ('store', 'video', 'weights_a', 'weights_b'):
        parser.add_argument(name)
    parser.add_argument('--frames', type=int, default=40)
    args = parser.parse_args()
    from ultralytics import YOLO
    store = Path(args.store)
    work = store.parents[1]
    model_a, model_b = YOLO(args.weights_a), YOLO(args.weights_b)
    tl = TrainingLabels(store)
    queue = tl.scene_queue()

    # (a) hand-drawn boxes
    scenes = []
    for s in queue:
        labs = tl.scene_labels(s['token'])
        drawn = [l['bbox'] for l in labs if l['origin'] == 'human_drawn']
        if drawn:
            scenes.append((s, cv2.imread(str(store / 'pending' / (s['token'] + '.jpg'))), drawn))
    total = sum(len(d) for _, _, d in scenes)
    total_eval = sum(len(d) for s, _, d in scenes if s['split'] == 'eval')
    print(f'(a) {len(scenes)} scenes, {total} drawn boxes ({total_eval} in eval scenes)')
    for conf_a in (0.25, 0.1):
        rows = {'A': [0, 0], 'union': [0, 0]}
        for s, image, drawn in scenes:
            h, w = image.shape[:2]
            cam = s['camera'] or 'cam3'
            found_a = tracker.detect(model_a, image, cam, 0, conf_a)
            found_b = tracker.detect(model_b, image, cam, 0, B_CONFIDENCE)
            both, _ = union(found_a, found_b)
            for name, dets in (('A', found_a), ('union', both)):
                for b in drawn:
                    t = [b[0] * w, b[1] * h, b[2] * w, b[3] * h]
                    if any(iou(t, d) >= 0.3 for d in dets):
                        rows[name][0] += 1
                        if s['split'] == 'eval':
                            rows[name][1] += 1
        for name, (ok, ok_eval) in rows.items():
            print(f'    A conf {conf_a}: {name:5s} found {ok}/{total} (eval {ok_eval}/{total_eval})')

    # (b) precision of boxes only the large model found, from the person-check answers
    answers = []
    for name in ('person-check1-answers.json', 'person-check2-answers.json'):
        path = work / name
        if path.is_file():
            answers += json.loads(path.read_text(encoding='utf-8'))
    for source in ('B', 'A'):
        rows = [a for a in answers if a['found_by'] == source and a.get('label') in ('ok', 'wrong')]
        ok = sum(1 for a in rows if a['label'] == 'ok')
        print(f'(b) found only by {source}: {ok}/{len(rows)} people ({100 * ok / max(1, len(rows)):.0f}%)')
    rows = [a for a in answers if a['found_by'] == 'B' and a.get('label') in ('ok', 'wrong') and a['score'] >= B_ADD]
    ok = sum(1 for a in rows if a['label'] == 'ok')
    print(f'    only B with score >= {B_ADD}: {ok}/{len(rows)} people; score range of all answered B boxes: '
          f'{min(a["score"] for a in answers if a["found_by"] == "B"):.2f}-{max(a["score"] for a in answers if a["found_by"] == "B"):.2f}')

    # (c) detections per frame and time on real match frames
    avoid = [s['clip_time'] for s in queue if s['split'] in ('eval', 'buffer_excluded') and s['clip_time'] is not None]
    cap = cv2.VideoCapture(args.video)
    fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
    seconds = count / fps
    times = [t for t in (70 + (seconds - 70) * (i + 0.5) / args.frames for i in range(args.frames)) if all(abs(t - a) > 15 for a in avoid)]
    n_a = n_u = n_added = 0
    time_a = time_b = 0.0
    used = 0
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, image = cap.read()
        if not ok:
            continue
        camera = camera_of(t)
        if camera is None:      # the cam2 part: no detector crop
            continue
        t0 = time.perf_counter()
        found_a = tracker.detect(model_a, image, camera, 0, 0.25)
        t1 = time.perf_counter()
        found_b = tracker.detect(model_b, image, camera, 0, B_CONFIDENCE)
        t2 = time.perf_counter()
        both, added = union(found_a, found_b)
        n_a += len(found_a)
        n_u += len(both)
        n_added += len(added)
        time_a += t1 - t0
        time_b += t2 - t1
        used += 1
    print(f'(c) {used} frames: A alone {n_a / used:.1f} per frame, union {n_u / used:.1f} per frame (+{n_added / used:.1f}); '
          f'seconds per frame: A {time_a / used:.2f}, B {time_b / used:.2f}, union {(time_a + time_b) / used:.2f}')


if __name__ == '__main__':
    main()
