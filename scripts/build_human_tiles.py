"""Training tiles from the boxes a human judged in the person-check sessions (research only; the labels of these boxes are human labels).

python scripts/build_human_tiles.py <video> <output folder> <weights A> <weights B> [--fold K --folds 2] [--with-auto] [--repeat 3]

Every judged box of work/person-check1-answers.json and person-check2-answers.json is used:
  * label ok    -> a person (human label),
  * label wrong -> background: the detection that was judged is taken out of the unclear boxes, so the tile teaches "no person here" (hard negative).
The rest of each frame is labelled as in scripts/build_auto_dataset.py (both detectors agree, or one is sure); a tile that still touches an unclear box is dropped.
Only tiles that touch a judged box are written. Frames within 15 s of an evaluation scene are not used.
Cross-validation: --fold K keeps out every frame whose five-minute block number modulo --folds equals K (those frames are the test frames of the fold, see scripts/bench_human_cv.py);
without --fold all frames are used. Writes <output>/fold<K|all>/{images,labels}/train and <output>/fold<K|all>.yaml (own match only: the 171 tiles of detector-ft-20261112,
optionally the 3,570 machine-labelled tiles of detector-auto-20261116 with --with-auto, and the human tiles repeated --repeat times).
"""
import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from app.training_labels import TrainingLabels  # noqa: E402
from build_auto_dataset import split_boxes, tile_rows  # noqa: E402
from build_pseudo_tiles import iou, starts, TILE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parents[1] / 'work'
STORE = WORK / 'human-labels' / 'public-own-match-review-20261111'
ANSWERS = [WORK / 'person-check1-answers.json', WORK / 'person-check2-answers.json']
BLOCK = 300.0


def fold_of(time, folds):
    return int(time // BLOCK) % folds


def judged_frames():
    """-> {(file number, time, camera): [rows]}"""
    frames = defaultdict(list)
    for number, path in enumerate(ANSWERS, start=1):
        for r in json.loads(path.read_text(encoding='utf-8')):
            frames[(number, r['time'], r['camera'])].append(r)
    return frames


def touches(box, x, y):
    return min(box[2], x + TILE) - max(box[0], x) > 0 and min(box[3], y + TILE) - max(box[1], y) > 0


def main():
    parser = argparse.ArgumentParser()
    for name in ('video', 'output', 'weights_a', 'weights_b'):
        parser.add_argument(name)
    parser.add_argument('--fold', type=int)
    parser.add_argument('--folds', type=int, default=2)
    parser.add_argument('--with-auto', action='store_true')
    parser.add_argument('--repeat', type=int, default=3)
    args = parser.parse_args()
    from ultralytics import YOLO
    name = f'fold{args.fold}' if args.fold is not None else 'foldall'
    out = Path(args.output) / name
    if out.exists():
        shutil.rmtree(out)
    for kind in ('images', 'labels'):
        (out / kind / 'train').mkdir(parents=True)
    avoid = [s['clip_time'] for s in TrainingLabels(str(STORE)).scene_queue() if s['split'] in ('eval', 'buffer_excluded') and s['clip_time'] is not None]
    a, b = YOLO(args.weights_a), YOLO(args.weights_b)
    cap = cv2.VideoCapture(args.video)
    stats = {'frames': 0, 'skipped_eval': 0, 'skipped_fold': 0, 'tiles': 0, 'dropped': 0, 'ok_boxes': 0, 'wrong_boxes': 0}
    times = []
    for (number, t, camera), rows in sorted(judged_frames().items()):
        if args.fold is not None and fold_of(t, args.folds) == args.fold:
            stats['skipped_fold'] += 1
            continue
        if any(abs(t - e) < 15 for e in avoid):
            stats['skipped_eval'] += 1
            continue
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, image = cap.read()
        if not ok:
            continue
        camera = camera if camera in tracker.PITCH_TOP else 'cam3'
        oks = [r['box'] for r in rows if r['label'] == 'ok']
        wrongs = [r['box'] for r in rows if r['label'] == 'wrong']
        judged = oks + wrongs
        if not judged:
            continue
        found_a, found_b = tracker.detect(a, image, camera, 0, 0.25), tracker.detect(b, image, camera, 0, 0.25)
        people, unclear = split_boxes(found_a, found_b, oks)
        unclear = [u for u in unclear if not any(iou(u, w) >= 0.5 for w in wrongs)]
        people = [p for p in people if not any(iou(p, w) >= 0.5 for w in wrongs)]
        stats['frames'] += 1
        stats['ok_boxes'] += len(oks)
        stats['wrong_boxes'] += len(wrongs)
        times.append(t)
        height, width = image.shape[:2]
        top = int(height * tracker.PITCH_TOP[camera])
        for y in [top + v for v in starts(height - top)]:
            for x in starts(width):
                if not any(touches(j, x, y) for j in judged):
                    continue
                tile_rows_ = tile_rows(people, unclear, x, y)
                if tile_rows_ is None:
                    stats['dropped'] += 1
                    continue
                for k in range(args.repeat):
                    stem = f'human_{number}_{int(t * 10):06d}_{x}_{y}_r{k}'
                    cv2.imwrite(str(out / 'images' / 'train' / (stem + '.jpg')), image[y:y + TILE, x:x + TILE], [cv2.IMWRITE_JPEG_QUALITY, 95])
                    (out / 'labels' / 'train' / (stem + '.txt')).write_text('\n'.join(tile_rows_) + ('\n' if tile_rows_ else ''), encoding='utf-8')
                stats['tiles'] += 1
    (Path(args.output) / f'{name}_times.json').write_text(json.dumps([{'time': t} for t in times]), encoding='utf-8')
    train = [str(WORK / 'detector-ft-20261112' / 'data' / 'images' / 'train')]
    if args.with_auto:
        train.append(str(WORK / 'detector-auto-20261116' / 'auto_new' / 'images' / 'train'))
    train.append(str((out / 'images' / 'train').resolve()))
    yaml = Path(args.output) / (name + ('_auto' if args.with_auto else '') + '.yaml')
    yaml.write_text('train:\n' + ''.join(f'  - {p.replace(chr(92), "/")}\n' for p in train) + f'val: {str(WORK / "detector-ft-20261112" / "data" / "images" / "val").replace(chr(92), "/")}\nnames:\n  0: person\n', encoding='utf-8')
    print(json.dumps(stats), '->', yaml)


if __name__ == '__main__':
    main()
