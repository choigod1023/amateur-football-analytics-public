"""Detect the people in every frame of the ball clips once and keep the boxes (for ball scoring that looks at the players).

Usage: python scripts/detect_clip_people.py <review store> <output folder> [--model yolo11n.pt] [--confidence 0.10] [--clips b01,b02,...]

Writes <output>/<clip>.json = {frame file: [[x1, y1, x2, y2, score], ...]} with the tiled detector of scripts/track_review_clip.py. Existing
files are skipped. The store is only read.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('output')
    parser.add_argument('--model', default='yolo11n.pt')
    parser.add_argument('--confidence', type=float, default=0.10)
    parser.add_argument('--clips')
    args = parser.parse_args()
    import cv2
    from ultralytics import YOLO
    import track_review_clip as tracker
    model = YOLO(args.model)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(args.store) / 'ball'
    index = json.loads((root / 'index.json').read_text(encoding='utf-8'))
    wanted = set(args.clips.split(',')) if args.clips else None
    for item in index['clips']:
        clip = item['id']
        target = out / f'{clip}.json'
        if target.exists() or (wanted and clip not in wanted):
            continue
        found = {}
        for frame in sorted((root / 'clips' / clip).glob('f_*.jpg')):
            image = cv2.imread(str(frame))
            found[frame.name] = [[round(float(v), 1) for v in d[:5]] for d in tracker.detect(model, image, item['camera'], 0, args.confidence)]
        target.write_text(json.dumps(found), encoding='utf-8')
        print(clip, sum(len(v) for v in found.values()), 'boxes', flush=True)


if __name__ == '__main__':
    main()
