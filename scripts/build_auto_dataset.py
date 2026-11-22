"""Turn the auto-labeller's bulk run into YOLO training tiles (research only; the labels are machine labels, not human ones).

python scripts/build_auto_dataset.py <bulk dir> <video> <output folder> <weights A> <weights B> [--start 0 --count 120]

A frame of the bulk run (candidates_*.jsonl) is detected again with both detectors. Boxes taken as people:
  * both detectors found it (IoU >= 0.5), or one of them with a score >= 0.6  ("sure", same rule as scripts/build_pseudo_tiles.py before the large model was trusted alone),
  * the boxes the auto-labeller accepted (decision accept in candidates, origin auto_labeller).
Every other detection (rejected, "a human must look", or in the grey zone between the two rules) is unclear: a 384 px tile that touches one is dropped, so an unclear person is never taught as background.
Tiles go to <output>/auto_new/images/train and labels/train; train_times.json lists the video seconds of the frames used so a benchmark can check that its test frames are not among them.
Run it in pieces (--start/--count over the frame indexes) to keep each GPU run short; existing tiles are never overwritten.
"""
import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from build_pseudo_tiles import iou, starts, TILE  # noqa: E402

SURE_SCORE = 0.6


def frames_of(bulk):
    frames = {}
    for path in sorted(glob.glob(str(Path(bulk) / 'candidates_*.jsonl'))):
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line)
                frames.setdefault(r['frame'], {'time': r['time'], 'camera': r['camera'], 'rows': []})['rows'].append(r)
    return frames


def split_boxes(found_a, found_b, accepted):
    """-> (people boxes, unclear boxes) from the detections of both models and the accepted candidates."""
    people = [a[:4] for a in found_a if any(iou(a, b) >= 0.5 for b in found_b) or a[4] >= SURE_SCORE]
    people += [b[:4] for b in found_b if b[4] >= SURE_SCORE and not any(iou(b, p) >= 0.5 for p in people)]
    people += [box for box in accepted if not any(iou(box, p) >= 0.5 for p in people)]
    unclear = [d[:4] for d in found_a + found_b if not any(iou(d, p) >= 0.5 for p in people)]
    return people, unclear


def tile_rows(people, unclear, x, y):
    """Label rows of one tile, or None when an unclear box touches it."""
    if any(min(b[2], x + TILE) - max(b[0], x) > 0 and min(b[3], y + TILE) - max(b[1], y) > 0 for b in unclear):
        return None
    rows = []
    for b in people:
        ix1, iy1, ix2, iy2 = max(b[0], x), max(b[1], y), min(b[2], x + TILE), min(b[3], y + TILE)
        area = (b[2] - b[0]) * (b[3] - b[1])
        if ix2 > ix1 and iy2 > iy1 and (ix2 - ix1) * (iy2 - iy1) >= 0.5 * area:
            rows.append(f'0 {((ix1 + ix2) / 2 - x) / TILE:.6f} {((iy1 + iy2) / 2 - y) / TILE:.6f} {(ix2 - ix1) / TILE:.6f} {(iy2 - iy1) / TILE:.6f}')
    return rows


def main():
    parser = argparse.ArgumentParser()
    for name in ('bulk', 'video', 'output', 'weights_a', 'weights_b'):
        parser.add_argument(name)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--count', type=int, default=0)
    parser.add_argument('--no-accepted', action='store_true', help='do not use the boxes the judge accepted (their precision is not checked by a human); only boxes both detectors agree on, or one is sure of')
    args = parser.parse_args()
    from ultralytics import YOLO
    out = Path(args.output) / 'auto_new'
    for kind in ('images', 'labels'):
        (out / kind / 'train').mkdir(parents=True, exist_ok=True)
    frames = frames_of(args.bulk)
    order = sorted(frames)
    chosen = order[args.start:args.start + args.count] if args.count else order
    a, b = YOLO(args.weights_a), YOLO(args.weights_b)
    cap = cv2.VideoCapture(args.video)
    times_path = Path(args.output) / 'train_times.json'
    times = json.loads(times_path.read_text(encoding='utf-8')) if times_path.exists() else []
    stats = {'frames': 0, 'tiles': 0, 'people': 0, 'tiles_dropped': 0, 'accepted_used': 0}
    for n in chosen:
        info = frames[n]
        cap.set(cv2.CAP_PROP_POS_MSEC, info['time'] * 1000)
        ok, image = cap.read()
        if not ok:
            continue
        camera = info['camera']
        found_a, found_b = tracker.detect(a, image, camera, 0, 0.25), tracker.detect(b, image, camera, 0, 0.25)
        accepted = [] if args.no_accepted else [r['box'] for r in info['rows'] if r['decision'] == 'accept']
        people, unclear = split_boxes(found_a, found_b, accepted)
        stats['frames'] += 1
        stats['accepted_used'] += len(accepted)
        height, width = image.shape[:2]
        top = int(height * tracker.PITCH_TOP[camera])
        for y in [top + v for v in starts(height - top)]:
            for x in starts(width):
                name = f'auto_{n:04d}_{x}_{y}'
                if (out / 'images' / 'train' / (name + '.jpg')).exists():
                    continue
                rows = tile_rows(people, unclear, x, y)
                if rows is None:
                    stats['tiles_dropped'] += 1
                    continue
                cv2.imwrite(str(out / 'images' / 'train' / (name + '.jpg')), image[y:y + TILE, x:x + TILE])
                (out / 'labels' / 'train' / (name + '.txt')).write_text('\n'.join(rows), encoding='utf-8')
                stats['tiles'] += 1
                stats['people'] += len(rows)
        times.append({'time': info['time'], 'frame': n})
    times_path.write_text(json.dumps(times), encoding='utf-8')
    print(json.dumps(stats))


if __name__ == '__main__':
    main()
