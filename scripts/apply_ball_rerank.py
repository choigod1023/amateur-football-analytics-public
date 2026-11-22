"""Find the ball in prepared clips with a trained re-ranker (scripts/train_ball_rerank.py) and link the picks into a ball path.

Usage: python scripts/apply_ball_rerank.py <review store> <model.pt> <people folder> <output json> [--linker balanced|strict|v1] [--threshold 0.7 (v1 only)] [--clips b37,b38,...]

For every clip: candidate circles (candidates.json) + the people boxes of scripts/detect_clip_people.py -> probabilities -> app/ball_path.py.
Output: {clip: {'camera', 'start', 'fps', 'path': {frame file: [x, y, probability]}}}. A frame without an entry means "unknown", not "no ball".
Historical threshold-0.7 evaluation reported 92.6% conditional precision on ball-present frames.
Including 140 predictions on empty frames, precision was 249/(249+20+140)=60.9%; ball-frame recall was 40.7%.
Those grouped clips do not establish independent-match or live performance.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.ball_path import BALANCED, STRICT, link_ball_path, link_ball_path_v2  # noqa: E402
from train_ball_rerank import Net, patch_of, tabular  # noqa: E402


def on_head(x, y, boxes):
    """True when (x, y) lies on the head of a person: inside the box horizontally and between 10 % of the body height above the box and 22 % below its top.
    A ball is on the ground or in the air next to people; a bright round spot on a head is a head, a light or a hat."""
    for b in boxes:
        height = b[3] - b[1]
        if b[0] <= x <= b[2] and b[1] - 0.10 * height <= y <= b[1] + 0.22 * height:
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('model')
    parser.add_argument('people')
    parser.add_argument('output')
    parser.add_argument('--linker', choices=('balanced', 'strict', 'v1'), default='balanced', help='balanced and strict are app.ball_path.link_ball_path_v2 presets; v1 uses --threshold')
    parser.add_argument('--threshold', type=float, default=0.7)
    parser.add_argument('--clips')
    parser.add_argument('--keep-heads', action='store_true', help='keep candidates that lie on the head of a person (dropped by default)')
    args = parser.parse_args()
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    net = Net().to(device)
    net.load_state_dict(torch.load(args.model, map_location=device))
    net.eval()
    root = Path(args.store) / 'ball'
    index = json.loads((root / 'index.json').read_text(encoding='utf-8'))
    wanted = set(args.clips.split(',')) if args.clips else None
    result = {}
    for item in index['clips']:
        clip = item['id']
        people_file = Path(args.people) / f'{clip}.json'
        if (wanted and clip not in wanted) or not people_file.exists():
            continue
        data = json.loads((root / 'clips' / clip / 'candidates.json').read_text(encoding='utf-8'))
        people = json.loads(people_file.read_text(encoding='utf-8'))
        frames = [{'file': e['file'], 'cands': e['cands']} for e in data['frames']]
        scored = []
        for number, frame in enumerate(frames):
            if not frame['cands']:
                scored.append([])
                continue
            image = cv2.imread(str(root / 'clips' / clip / frame['file']))
            patches = torch.tensor(np.stack([(patch_of(image, c[0], c[1]).astype(np.float32) / 255).transpose(2, 0, 1) for c in frame['cands']])).to(device)
            tabs = torch.tensor(np.stack([np.array(tabular(frames, number, c, people.get(frame['file'], [])), np.float32) for c in frame['cands']])).to(device)
            with torch.no_grad():
                p = torch.sigmoid(net(patches, tabs)).cpu().numpy()
            boxes = people.get(frame['file'], [])
            scored.append([(c[0], c[1], float(q)) for c, q in zip(frame['cands'], p) if args.keep_heads or not on_head(c[0], c[1], boxes)])
        picks = link_ball_path(scored, threshold=args.threshold) if args.linker == 'v1' else link_ball_path_v2(scored, **(BALANCED if args.linker == 'balanced' else STRICT))
        result[clip] = {'camera': item['camera'], 'start': item['start'], 'fps': index.get('fps', 5),
                        'path': {frames[i]['file']: [round(v, 3) for v in pick] for i, pick in picks.items()}}
        print(clip, f'{len(picks)} of {len(frames)} frames answered', flush=True)
    Path(args.output).write_text(json.dumps(result), encoding='utf-8')


if __name__ == '__main__':
    main()
