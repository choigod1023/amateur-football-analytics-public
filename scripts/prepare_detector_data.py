"""Build a tiled person-detection dataset (YOLO format) from the human labels of the review store (read only).

Usage: python scripts/prepare_detector_data.py <review store> <output folder> [--tile 384] [--stride 192] [--top 0.45]

Train images: labelled scenes whose split is not "eval", plus pending scenes that contain boxes drawn by hand (their
automatic candidates with score >= 0.5 count as people too, the rest of such a scene is unchecked).
Validation images: labelled scenes with split "eval" (the reviewer checked every person in them).
People are boxes with role player, goalkeeper, referee or spectator, and every box drawn by hand. Boxes with role
duplicate, shadow or unknown are left out and the tile around them is skipped, so they never count as background.
Each photo is cut into tiles of the same size the detector uses at run time (384 px, shown to the model at 768 px).
"""
import argparse
import json
import sys
from pathlib import Path

PEOPLE = ('player', 'goalkeeper', 'referee', 'spectator')
SKIP = ('duplicate', 'shadow', 'unknown')


def tile_boxes(boxes, width, height, tile=384, stride=192, top=0.45, min_visible=0.5, skip_boxes=()):
    """boxes: [(x1, y1, x2, y2)] in pixels. Returns [(x, y, [(cls, cx, cy, w, h) normalised to the tile])] for tiles below `top`.

    A box is kept in a tile when at least `min_visible` of its area lies inside it. A tile that holds a skip box (a box
    whose label is unclear) is dropped altogether so that unclear people are never taught as background.
    """
    def starts(total):
        found = list(range(0, max(1, total - tile + 1), stride))
        if found[-1] != max(0, total - tile):
            found.append(max(0, total - tile))
        return found
    first = int(height * top)
    tiles = []
    for y in [first + v for v in starts(height - first)]:
        for x in starts(width):
            if any(min(b[2], x + tile) - max(b[0], x) > 0 and min(b[3], y + tile) - max(b[1], y) > 0 for b in skip_boxes):
                continue
            rows = []
            for b in boxes:
                ix1, iy1, ix2, iy2 = max(b[0], x), max(b[1], y), min(b[2], x + tile), min(b[3], y + tile)
                area = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                full = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
                if area / full >= min_visible and ix2 > ix1 and iy2 > iy1:
                    rows.append((0, ((ix1 + ix2) / 2 - x) / tile, ((iy1 + iy2) / 2 - y) / tile, (ix2 - ix1) / tile, (iy2 - iy1) / tile))
            tiles.append((x, y, rows))
    return tiles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('output')
    parser.add_argument('--tile', type=int, default=384)
    parser.add_argument('--stride', type=int, default=192)
    parser.add_argument('--top', type=float, default=0.45)
    args = parser.parse_args()
    import cv2

    store, out = Path(args.store), Path(args.output)
    scenes = {}                       # photo -> {'split', 'boxes', 'skip'}
    for path in store.glob('*.json'):
        try:
            label = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(label, dict) or 'bbox_image_norm' not in label or not (store / label['image']).is_file():
            continue
        scene = scenes.setdefault(label['image'], {'split': (label.get('source_provenance') or {}).get('split'), 'boxes': [], 'skip': [], 'weak': False})
        box = label['bbox_image_norm']
        if label.get('role') in PEOPLE or label.get('annotation_origin') == 'human_drawn' and label.get('role') not in SKIP:
            scene['boxes'].append(box)
        elif label.get('role') in SKIP:
            scene['skip'].append(box)
    for path in (store / 'pending').glob('*.json'):
        try:
            meta = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        image = path.with_suffix('.jpg')
        people = meta.get('people', []) if isinstance(meta, dict) else []
        drawn = [p['bbox'] for p in people if p.get('annotation_origin') == 'human_drawn']
        if not drawn or image.name in scenes or not image.is_file():
            continue
        confident = [p['bbox'] for p in people if p.get('annotation_origin') == 'model_candidate' and (p.get('detector_score') or 0) >= 0.5]
        scenes[str(Path('pending') / image.name)] = {'split': (meta.get('source_provenance') or {}).get('split'), 'boxes': drawn + confident, 'skip': [], 'weak': True}
    counts = {'train': [0, 0, 0], 'val': [0, 0, 0]}
    for name, scene in scenes.items():
        part = 'val' if scene['split'] == 'eval' else 'train'
        image = cv2.imread(str(store / name))
        height, width = image.shape[:2]
        px = lambda b: (b[0] * width, b[1] * height, b[2] * width, b[3] * height)
        tiles = tile_boxes([px(b) for b in scene['boxes']], width, height, args.tile, args.stride, args.top, skip_boxes=[px(b) for b in scene['skip']])
        for x, y, rows in tiles:
            stem = f"{Path(name).stem}_{x}_{y}"
            for sub in ('images', 'labels'):
                (out / sub / part).mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out / 'images' / part / (stem + '.jpg')), image[y:y + args.tile, x:x + args.tile], [cv2.IMWRITE_JPEG_QUALITY, 95])
            (out / 'labels' / part / (stem + '.txt')).write_text(''.join(f'{c} {a:.6f} {b:.6f} {w:.6f} {h:.6f}\n' for c, a, b, w, h in rows), encoding='utf-8')
            counts[part][0] += 1
            counts[part][1] += len(rows)
        counts[part][2] += 1
    (out / 'data.yaml').write_text(f"path: {out.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: person\n", encoding='utf-8')
    print({part: {'tiles': c[0], 'people': c[1], 'photos': c[2]} for part, c in counts.items()})
    print('weakly checked photos (hand-drawn boxes plus candidates >= 0.5):', sum(1 for s in scenes.values() if s['weak']))


if __name__ == '__main__':
    main()
