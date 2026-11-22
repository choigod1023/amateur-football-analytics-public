"""Pseudo-label tiles of this match from two detectors that must agree (research only, nothing is deployed).

Usage: python scripts/build_pseudo_tiles.py <review store> <video> <base dataset> <output dataset> <weights A> <weights B> [--frames 400]

Frames are taken evenly from the video, never within 15 s of an evaluation scene. Both detectors run on the same 384 px tiles the tracker uses.
A person is a teacher label when both detectors find it (IoU >= 0.5) or the first one is sure (score >= 0.6) or the second one alone has score >= SECOND_SURE. A box that only one detector finds with a lower score is
unclear: its tile is dropped so that it never counts as background. The base dataset is copied into the output, the new tiles are added to train only.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from app.camera_segments import camera_of  # noqa: E402
from app.training_labels import TrainingLabels  # noqa: E402

TILE, STRIDE = 384, 192
SECOND_SURE = 0.35   # the second detector (large model) alone is trusted from this score: 29 of 34 such boxes were people in the person-check1 answers (the first detector alone: 9 of 26)


def iou(a, b):
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    i = w * h
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def teacher(found_a, found_b):
    """-> (sure boxes, unclear boxes)."""
    sure, unclear, used = [], [], set()
    for a in found_a:
        match = next((j for j, b in enumerate(found_b) if j not in used and iou(a, b) >= 0.5), None)
        if match is not None:
            used.add(match)
            sure.append(a[:4])
        elif a[4] >= 0.6:
            sure.append(a[:4])
        else:
            unclear.append(a[:4])
    for j, b in enumerate(found_b):
        if j not in used:
            (sure if b[4] >= SECOND_SURE else unclear).append(b[:4])
    return sure, unclear


def starts(total):
    found = list(range(0, max(1, total - TILE + 1), STRIDE))
    if found[-1] != max(0, total - TILE):
        found.append(max(0, total - TILE))
    return found


def main():
    parser = argparse.ArgumentParser()
    for name in ('store', 'video', 'base', 'output', 'weights_a', 'weights_b'):
        parser.add_argument(name)
    parser.add_argument('--frames', type=int, default=400)
    args = parser.parse_args()
    from ultralytics import YOLO
    out = Path(args.output)
    if out.exists():
        raise SystemExit('output exists')
    shutil.copytree(args.base, out)
    for line in (out / 'data.yaml').read_text(encoding='utf-8').splitlines():
        pass
    (out / 'data.yaml').write_text(f'path: {out.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: person\n', encoding='utf-8')
    avoid = [s['clip_time'] for s in TrainingLabels(args.store).scene_queue() if s['split'] in ('eval', 'buffer_excluded') and s['clip_time'] is not None]
    cap = cv2.VideoCapture(args.video)
    fps, total = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
    seconds = total / fps
    times = [t for t in (seconds * (i + 0.5) / args.frames for i in range(args.frames)) if all(abs(t - a) > 15 for a in avoid) and t > 70]
    model_a, model_b = YOLO(args.weights_a), YOLO(args.weights_b)
    tiles = boxes_total = skipped = 0
    for n, t in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, image = cap.read()
        if not ok:
            continue
        camera = camera_of(t)
        if camera is None:      # the cam2 part: no detector crop
            continue
        sure, unclear = teacher(tracker.detect(model_a, image, camera, 0, 0.25), tracker.detect(model_b, image, camera, 0, 0.25))
        height, width = image.shape[:2]
        top = int(height * tracker.PITCH_TOP[camera])
        for y in [top + v for v in starts(height - top)]:
            for x in starts(width):
                if any(min(b[2], x + TILE) - max(b[0], x) > 0 and min(b[3], y + TILE) - max(b[1], y) > 0 for b in unclear):
                    skipped += 1
                    continue
                rows = []
                for b in sure:
                    ix1, iy1, ix2, iy2 = max(b[0], x), max(b[1], y), min(b[2], x + TILE), min(b[3], y + TILE)
                    area = (b[2] - b[0]) * (b[3] - b[1])
                    if ix2 > ix1 and iy2 > iy1 and (ix2 - ix1) * (iy2 - iy1) >= 0.5 * area:
                        rows.append(f'0 {((ix1 + ix2) / 2 - x) / TILE:.6f} {((iy1 + iy2) / 2 - y) / TILE:.6f} {(ix2 - ix1) / TILE:.6f} {(iy2 - iy1) / TILE:.6f}')
                name = f'pseudo_{n}_{x}_{y}'
                cv2.imwrite(str(out / 'images' / 'train' / (name + '.jpg')), image[y:y + TILE, x:x + TILE])
                (out / 'labels' / 'train' / (name + '.txt')).write_text('\n'.join(rows), encoding='utf-8')
                tiles += 1
                boxes_total += len(rows)
        if n % 20 == 0:
            print(n, len(times), tiles, boxes_total, skipped, flush=True)
    print('frames', len(times), 'tiles', tiles, 'boxes', boxes_total, 'unclear tiles dropped', skipped)


if __name__ == '__main__':
    main()
