"""Train and evaluate a re-ranker that picks the ball among the candidate circles of the ball clips (read only on the review store).

Usage: python scripts/train_ball_rerank.py <review store> <output folder> [--folds 5] [--epochs 30] [--people <folder from detect_clip_people.py>]

Every candidate circle (see scripts/prepare_ball_clips.py) of a frame is a sample: positive when it lies within 6 px of the ball a
person labelled in that frame, negative otherwise (including every candidate of frames labelled "none"). Frames labelled "unsure" and
labels the reviewer rejected are left out. A small network looks at a 32 px patch around the candidate plus a few numbers (detector
score, position, how well the neighbouring frames support it). Evaluation holds out whole clips (grouped folds); the final model is
trained on every clip and written to <output>/model.pt. metrics.json has the held-out numbers next to those of the detector score alone.
The candidates came from a detector and the people could only choose among them, so recall is measured against candidates, not against
every ball that may be in the picture.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ball_path import link_ball_path  # noqa: E402

PATCH = 32
TAB = 14


def load_clips(store):
    clips = {}
    for label_file in sorted((Path(store) / 'ball' / 'labels').glob('b*.json')):
        clip = label_file.stem
        labels = json.loads(label_file.read_text(encoding='utf-8'))
        data = json.loads((Path(store) / 'ball' / 'clips' / clip / 'candidates.json').read_text(encoding='utf-8'))
        camera = data.get('camera', 'cam1')
        frames = []
        for entry in data['frames']:
            label = labels.get(entry['file'], {})
            state = label.get('state')
            if state == 'ball' and label.get('verified') == 'rejected':
                state = 'skip'
            if state not in ('ball', 'none'):
                state = 'skip'
            frames.append({'file': entry['file'], 'cands': entry['cands'], 'state': state, 'ball': (label.get('x'), label.get('y')) if state == 'ball' else None})
        clips[clip] = {'camera': camera, 'frames': frames}
    return clips


def patch_of(image, x, y):
    half = PATCH // 2
    padded = cv2.copyMakeBorder(image, half, half, half, half, cv2.BORDER_REFLECT)
    x, y = int(round(x)), int(round(y))
    crop = padded[y:y + PATCH, x:x + PATCH]
    return crop


def people_features(boxes, x, y):
    """How the candidate sits among the people of the frame: distance to the nearest feet (in body heights), whether it lies inside a body
    box and how high in it, and how many people stand within 150 px."""
    nearest, inside, height_share, close = 9.0, 0.0, 0.0, 0
    for x1, y1, x2, y2, _ in boxes:
        height = max(1.0, y2 - y1)
        nearest = min(nearest, math.hypot(x - (x1 + x2) / 2, y - y2) / height)
        if x1 <= x <= x2 and y1 <= y <= y2:
            inside, height_share = 1.0, (y - y1) / height
        if math.hypot(x - (x1 + x2) / 2, y - (y1 + y2) / 2) < 150:
            close += 1
    return [min(nearest, 9.0) / 9, inside, height_share, close / 6]


def tabular(frames, index, cand, people=None):
    x, y, score = cand
    around = {}
    for step in (-1, 1):
        j = index + step
        near = [c for c in frames[j]['cands'] if math.hypot(c[0] - x, c[1] - y) < 60] if 0 <= j < len(frames) else []
        around[step] = (len(near), max([c[2] for c in near], default=0.0), min([math.hypot(c[0] - x, c[1] - y) for c in near], default=60.0) / 60)
    count = len(frames[index]['cands'])
    rank = sorted((c[2] for c in frames[index]['cands']), reverse=True).index(score) if count else 0
    extra = people_features(people or [], x, y) if people is not None else [0.0, 0.0, 0.0, 0.0]
    return [score, y / 1080, x / 1920, rank / max(1, count), count / 20, around[-1][0] / 3, around[-1][1], around[1][0] / 3, around[1][1], (around[-1][2] + around[1][2]) / 2] + extra


def samples_of(store, clips, people_folder=None):
    rows = []
    for clip, data in clips.items():
        people = json.loads((Path(people_folder) / f'{clip}.json').read_text(encoding='utf-8')) if people_folder and (Path(people_folder) / f'{clip}.json').exists() else None
        for index, frame in enumerate(data['frames']):
            if frame['state'] == 'skip' or not frame['cands']:
                continue
            image = cv2.imread(str(Path(store) / 'ball' / 'clips' / clip / frame['file']))
            for cand in frame['cands']:
                label = 1 if frame['ball'] and math.hypot(cand[0] - frame['ball'][0], cand[1] - frame['ball'][1]) <= 6 else 0
                patch = patch_of(image, cand[0], cand[1]).astype(np.float32) / 255
                rows.append({'clip': clip, 'frame': index, 'cand': cand, 'patch': patch.transpose(2, 0, 1), 'tab': np.array(tabular(data['frames'], index, cand, people.get(frame['file']) if people is not None else None), np.float32), 'y': label})
    return rows


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv2d(3, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2), nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                                  nn.Conv2d(32, 32, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d(1), nn.Flatten())
        self.head = nn.Sequential(nn.Linear(32 + TAB, 32), nn.ReLU(), nn.Dropout(0.2), nn.Linear(32, 1))

    def forward(self, patch, tab):
        return self.head(torch.cat([self.conv(patch), tab], 1)).squeeze(1)


def train(rows, epochs, device, seed=0):
    torch.manual_seed(seed)
    patches = torch.tensor(np.stack([r['patch'] for r in rows])).to(device)
    tabs = torch.tensor(np.stack([r['tab'] for r in rows])).to(device)
    target = torch.tensor([float(r['y']) for r in rows]).to(device)
    net = Net().to(device)
    optimiser = torch.optim.Adam(net.parameters(), lr=2e-3, weight_decay=1e-4)
    weight = torch.tensor(min(40.0, (len(rows) - target.sum().item()) / max(1.0, target.sum().item()))).to(device)
    loss = nn.BCEWithLogitsLoss(pos_weight=weight)
    for _ in range(epochs):
        net.train()
        order = torch.randperm(len(rows), device=device)
        for start in range(0, len(rows), 256):
            pick = order[start:start + 256]
            flip = torch.rand(len(pick), device=device) < 0.5
            batch = patches[pick]
            batch = torch.where(flip[:, None, None, None], batch.flip(3), batch)
            optimiser.zero_grad()
            loss(net(batch, tabs[pick]), target[pick]).backward()
            optimiser.step()
    net.eval()
    return net


def predict(net, rows, device):
    with torch.no_grad():
        out = []
        for start in range(0, len(rows), 1024):
            chunk = rows[start:start + 1024]
            patches = torch.tensor(np.stack([r['patch'] for r in chunk])).to(device)
            tabs = torch.tensor(np.stack([r['tab'] for r in chunk])).to(device)
            out.append(torch.sigmoid(net(patches, tabs)).cpu().numpy())
    return np.concatenate(out)


def evaluate(clips, rows, probabilities, threshold=0.5):
    """Frame level numbers: the best candidate of every frame against the label, and the linked ball path."""
    by_frame = {}
    for row, p in zip(rows, probabilities):
        by_frame.setdefault((row['clip'], row['frame']), []).append((row['cand'], float(p), row['y']))
    top_right = top_total = 0
    detector_right = 0
    for items in by_frame.values():
        if any(y for _, _, y in items):
            top_total += 1
            top_right += max(items, key=lambda i: i[1])[2]
            detector_right += max(items, key=lambda i: i[0][2])[2]
    chain = {'right': 0, 'wrong': 0, 'ball_frames': 0, 'on_empty': 0, 'empty_frames': 0}
    for clip, data in clips.items():
        frames = []
        for index, frame in enumerate(data['frames']):
            items = by_frame.get((clip, index), [])
            frames.append([(c[0], c[1], p) for c, p, _ in items])
        picks = link_ball_path(frames, threshold=threshold)
        for index, frame in enumerate(data['frames']):
            if frame['state'] == 'ball':
                chain['ball_frames'] += 1
                if index in picks:
                    chain['right' if math.hypot(picks[index][0] - frame['ball'][0], picks[index][1] - frame['ball'][1]) <= 10 else 'wrong'] += 1
            elif frame['state'] == 'none':
                chain['empty_frames'] += 1
                chain['on_empty'] += index in picks
    return {'frames_with_ball': top_total, 'top1_reranker': round(top_right / max(1, top_total), 3), 'top1_detector_score': round(detector_right / max(1, top_total), 3), 'chain': chain}


def chain_metrics(chain):
    """Keep legacy conditional precision; include empty-frame false alarms explicitly."""
    conditional = round(chain['right'] / max(1, chain['right'] + chain['wrong']), 3)
    return {**chain, 'precision': conditional,
            'precision_definition': 'legacy: conditional on ball-present frames; use overall_precision',
            'conditional_precision_ball_present': conditional,
            'overall_precision': round(chain['right'] / max(1, chain['right'] + chain['wrong'] + chain['on_empty']), 3),
            'recall': round(chain['right'] / max(1, chain['ball_frames']), 3),
            'false_on_empty_share': round(chain['on_empty'] / max(1, chain['empty_frames']), 3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('output')
    parser.add_argument('--folds', type=int, default=5)
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--people')
    parser.add_argument('--seeds', type=int, default=1, help='networks trained with different seeds whose answers are averaged')
    parser.add_argument('--only', help='comma separated clips to use (for example the labelled ones)')
    args = parser.parse_args()
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    clips = load_clips(args.store)
    if args.only:
        clips = {k: v for k, v in clips.items() if k in set(args.only.split(','))}
    rows = samples_of(args.store, clips, args.people)
    names = sorted({r['clip'] for r in rows})
    print('clips', len(names), 'samples', len(rows), 'positives', sum(r['y'] for r in rows), flush=True)
    folds = [names[i::args.folds] for i in range(args.folds)]
    probabilities = np.zeros(len(rows))
    for held in folds:
        train_rows = [r for r in rows if r['clip'] not in held]
        nets = [train(train_rows, args.epochs, device, seed=k) for k in range(args.seeds)]
        index = [i for i, r in enumerate(rows) if r['clip'] in held]
        probabilities[index] = np.mean([predict(n, [rows[i] for i in index], device) for n in nets], axis=0)
        print('fold', held, 'done', flush=True)
    result = evaluate({n: clips[n] for n in names}, rows, probabilities)
    result['threshold_sweep'] = {}
    for threshold in (0.5, 0.7, 0.8, 0.9, 0.95, 0.98):
        chain = evaluate({n: clips[n] for n in names}, rows, probabilities, threshold)['chain']
        result['threshold_sweep'][str(threshold)] = chain_metrics(chain)
    np.save(Path(args.output) / 'cv_probabilities.npy', probabilities) if Path(args.output).is_dir() else None
    cams = {}
    for camera in sorted({c['camera'] for c in clips.values()}):
        subset = {n: clips[n] for n in names if clips[n]['camera'] == camera}
        mask = [i for i, r in enumerate(rows) if r['clip'] in subset]
        cams[camera] = evaluate(subset, [rows[i] for i in mask], probabilities[mask])
    result['by_camera'] = cams
    result['note'] = 'held-out clips (grouped folds); candidates came from a detector and people could only choose among them'
    print(json.dumps(result, ensure_ascii=False, indent=1))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    net = train(rows, args.epochs, device)
    torch.save(net.state_dict(), out / 'model.pt')


if __name__ == '__main__':
    main()
