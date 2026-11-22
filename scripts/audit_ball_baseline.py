"""CPU replay of stored ball candidates. Labels are used only after inference."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_ball_rerank import on_head
from app.ball_path import link_ball_path
from train_ball_rerank import Net, patch_of, tabular


def score(labels, predictions, radius=12):
    counts = dict(ball=0, empty=0, correct=0, wrong=0, missed=0, false_on_empty=0, excluded=0)
    distances = []
    for name, label in labels.items():
        pred = predictions.get(name)
        if label.get('state') == 'ball' and label.get('verified') in ('ok', 'moved'):
            counts['ball'] += 1
            if pred is None:
                counts['missed'] += 1
            else:
                distance = math.hypot(pred[0] - label['x'], pred[1] - label['y'])
                counts['correct' if distance <= radius else 'wrong'] += 1
                distances.append(distance)
        elif label.get('state') == 'none':
            counts['empty'] += 1
            counts['false_on_empty'] += pred is not None
        else:
            counts['excluded'] += 1
    denom = counts['correct'] + counts['wrong'] + counts['false_on_empty']
    return {**counts, 'precision': counts['correct'] / denom if denom else None,
            'recall': counts['correct'] / counts['ball'] if counts['ball'] else None,
            'answered_ball_error_median_px': float(np.median(distances)) if distances else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    torch.set_num_threads(2)
    store = args.root / 'work/human-labels/public-own-match-review-20261111/ball'
    model = args.root / 'work/ball-rerank-v2/model.pt'
    people_dir = args.root / 'work/ball-people-20261112'
    net = Net().cpu().eval()
    net.load_state_dict(torch.load(model, map_location='cpu', weights_only=True))
    all_labels, methods, manifest = {}, {}, {}
    started = time.perf_counter()
    for label_file in sorted((store / 'labels').glob('b*.json')):
        clip = label_file.stem
        if int(clip[1:]) < 37:
            continue
        labels = json.loads(label_file.read_text(encoding='utf-8'))
        frames = json.loads((store / 'clips' / clip / 'candidates.json').read_text())['frames']
        people = json.loads((people_dir / (clip + '.json')).read_text())
        raw, selected, scored, unmasked, oracle = {}, {}, [], [], []
        for i, frame in enumerate(frames):
            name, cands = frame['file'], frame['cands']
            probabilities = []
            if cands:
                image = cv2.imread(str(store / 'clips' / clip / name))
                patches = torch.tensor(np.stack([(patch_of(image, c[0], c[1]).astype(np.float32) / 255).transpose(2, 0, 1) for c in cands]))
                tabs = torch.tensor(np.array([tabular(frames, i, c, people.get(name, [])) for c in cands], dtype=np.float32))
                with torch.inference_mode():
                    probabilities = torch.sigmoid(net(patches, tabs)).numpy()
                raw[name] = max(cands, key=lambda c: c[2])
            values = [(c[0], c[1], float(p)) for c, p in zip(cands, probabilities)]
            unmasked.append(values)
            scored.append([v for v in values if not on_head(v[0], v[1], people.get(name, []))])
            if values and max(v[2] for v in values) >= .7:
                selected[name] = max(values, key=lambda v: v[2])
            # Diagnostic upper bound only; never used to choose actual predictions.
            label = labels.get(name, {})
            near = [c for c in cands if label.get('state') == 'ball' and label.get('verified') in ('ok', 'moved') and math.hypot(c[0]-label['x'], c[1]-label['y']) <= 12]
            oracle.append([(near[0][0], near[0][1], 1.)] if near else [])
        outputs = {'raw_top1': raw, 'rerank_top1_07': selected,
                   'path_07_head_filter': {frames[i]['file']: v for i, v in link_ball_path(scored, threshold=.7).items()},
                   'path_07_no_head_filter': {frames[i]['file']: v for i, v in link_ball_path(unmasked, threshold=.7).items()},
                   'candidate_oracle': {frames[i]['file']: v[0] for i, v in enumerate(oracle) if v}}
        for method, values in outputs.items():
            methods.setdefault(method, {}).update({clip+'/'+k: v for k, v in values.items()})
        all_labels.update({clip+'/'+k: v for k, v in labels.items()})
        manifest[str(label_file)] = hashlib.sha256(label_file.read_bytes()).hexdigest()
        print(clip, len(frames), 'replayed', flush=True)
    result = {'scope': 'stored-candidate CPU replay; not live or independent-match validation',
              'radius_px': 12, 'threshold': .7, 'elapsed_seconds': time.perf_counter()-started,
              'model_sha256': hashlib.sha256(model.read_bytes()).hexdigest(), 'label_sha256': manifest,
              'metrics': {key: score(all_labels, value) for key, value in methods.items()}}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'metrics.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (args.output/'predictions.json').write_text(json.dumps(methods), encoding='utf-8')
    print(json.dumps(result['metrics'], indent=2))


if __name__ == '__main__':
    main()
