"""Train and evaluate a small team and role classifier from the human labels of the review store (read only).

Usage: python scripts/train_team_role.py <review store folder> <output folder> [--holdout names.json]

--holdout: a JSON list of photo file names (for example ["abc.jpg"]) that are kept out of every step of training and are only used
to measure the finished model; the accuracy on them is written to metrics.json as 'holdout'.

Evaluation holds out one whole scene at a time, so the boxes of one photo never sit on both sides. The result is
printed and written to metrics.json; the final model (trained on every usable box) goes to model.pt in the output
folder. The store is never modified. Only the 11 or so labelled scenes of one match are available, so the numbers
say little about other cameras or matches.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.team_role_features import CLASSES, FEATURE_NAMES, box_features, class_of  # noqa: E402

HIDDEN, EPOCHS, SEEDS = 24, 500, 3


def load(store):
    """Read observations for evaluation; this does NOT select training rows.

    Every training caller must apply training_mask before fit. Kept separate so
    evaluation readers can still inspect held-out labels without modifying them.
    """
    rows, images = [], {}
    for path in sorted(Path(store).glob('*.json')):
        try:
            label = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(label, dict) or 'bbox_image_norm' not in label:
            continue
        cls = class_of(label.get('role'), label.get('team_group'))
        if cls is None:
            continue
        name = label['image']
        if name not in images:
            images[name] = cv2.imread(str(Path(store) / name))
        if images[name] is None:
            continue
        rows.append((name, box_features(images[name], label['bbox_image_norm']), CLASSES.index(cls)))
    return [r[0] for r in rows], np.array([r[1] for r in rows]), np.array([r[2] for r in rows])


def scene_splits(store):
    """Missing, mixed, or unknown split metadata must never silently mean train."""
    groups = {}
    for path in sorted(Path(store).glob('*.json')):
        try:
            row = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(row, dict) and 'bbox_image_norm' in row:
            groups.setdefault(row['image'], set()).add((row.get('source_provenance') or {}).get('split', 'unassigned'))
    return {name: next(iter(values)) if len(values) == 1 else 'conflicting' for name, values in groups.items()}


def training_mask(store, scenes):
    splits = scene_splits(store)
    return np.asarray([splits.get(str(name)) == 'train' for name in scenes], dtype=bool)


def validate_image_split(store, scenes, train_mask, eval_mask):
    """Reject renamed copies of evaluation images in a training partition."""
    import hashlib
    scenes=np.asarray(scenes)
    hashes={str(s):hashlib.sha256((Path(store)/str(s)).read_bytes()).hexdigest() for s in set(scenes)}
    if {hashes[str(s)] for s in scenes[train_mask]} & {hashes[str(s)] for s in scenes[eval_mask]}:
        raise ValueError('Duplicate image leaks across train/eval boundary')
    return hashes


def fit(train_x, train_y, test_x):
    mean, spread = train_x.mean(0), train_x.std(0) + 1e-6
    a, b, t = torch.tensor((train_x - mean) / spread), torch.tensor((test_x - mean) / spread), torch.tensor(train_y)
    weights = torch.tensor([len(train_y) / (len(CLASSES) * max(1, (train_y == k).sum())) for k in range(len(CLASSES))], dtype=torch.float32)
    probability, nets = 0, []
    for seed in range(SEEDS):
        torch.manual_seed(seed)
        net = nn.Sequential(nn.Linear(a.shape[1], HIDDEN), nn.ReLU(), nn.Dropout(.2), nn.Linear(HIDDEN, len(CLASSES)))
        optimiser = torch.optim.Adam(net.parameters(), lr=3e-3, weight_decay=1e-3)
        loss = nn.CrossEntropyLoss(weight=weights)
        for _ in range(EPOCHS):
            net.train()
            optimiser.zero_grad()
            loss(net(a), t).backward()
            optimiser.step()
        net.eval()
        probability = probability + torch.softmax(net(b), 1).detach().numpy() / SEEDS
        nets.append(net.state_dict())
    return probability, nets, mean, spread


def main():
    args = sys.argv[1:]
    held = set()
    if '--holdout' in args:
        held = set(json.loads(Path(args[args.index('--holdout') + 1]).read_text(encoding='utf-8')))
        del args[args.index('--holdout'):args.index('--holdout') + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    scenes, x, y = load(args[0])
    out = Path(args[1])
    scenes = np.array(scenes)
    splits = scene_splits(args[0])
    hold = np.isin(scenes, list(held)) | np.asarray([splits.get(str(s)) == 'eval' for s in scenes])
    train_mask = training_mask(args[0], scenes) & ~hold
    if not train_mask.any():
        raise SystemExit('No explicitly train-labelled scenes; unassigned and missing split are excluded')
    hashes = validate_image_split(args[0],scenes,train_mask,hold)
    hold_x, hold_y = x[hold], y[hold]
    split_manifest = {'train_images':sorted(set(scenes[train_mask])), 'eval_images':sorted(set(scenes[hold])),
                      'excluded_images':sorted(set(scenes[~train_mask & ~hold])), 'image_sha256':hashes,
                      'policy':'only explicit source_provenance.split=train may train; eval/buffer/unassigned excluded'}
    scenes, x, y = scenes[train_mask], x[train_mask], y[train_mask]
    out.mkdir(parents=True, exist_ok=True)
    (out/'split-manifest.json').write_text(json.dumps(split_manifest,indent=2),encoding='utf-8')
    print('usable boxes', len(y), dict(Counter(CLASSES[k] for k in y)), 'scenes', len(set(scenes)))
    scenes = np.array(scenes)
    predicted = np.zeros(len(y), int)
    for scene in sorted(set(scenes)):
        held = scenes == scene
        if len(set(y[~held])) < len(CLASSES):
            raise SystemExit(f'Scene {scene[:8]} leaves a class without training examples')
        predicted[held] = fit(x[~held], y[~held], x[held])[0].argmax(1)
    confusion = np.zeros((len(CLASSES), len(CLASSES)), int)
    for truth, guess in zip(y, predicted):
        confusion[truth, guess] += 1
    metrics = {'boxes': int(len(y)), 'scenes': int(len(set(scenes))), 'accuracy': round(float((predicted == y).mean()), 3),
               'recall': {c: round(float((predicted[y == k] == k).mean()), 3) for k, c in enumerate(CLASSES)},
               'confusion_rows_true_cols_predicted': confusion.tolist(), 'classes': list(CLASSES),
               'per_scene_accuracy': {s[:8]: round(float((predicted[scenes == s] == y[scenes == s]).mean()), 3) for s in sorted(set(scenes))},
               'note': 'leave-one-scene-out on one match; not a measure for other cameras or matches'}
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    _, nets, mean, spread = fit(x, y, x[:1])
    if len(hold_y):
        probabilities = fit(x, y, hold_x)[0]
        guess = probabilities.argmax(1)
        metrics['holdout'] = {'boxes': int(len(hold_y)), 'accuracy': round(float((guess == hold_y).mean()), 3),
                              'recall': {c: round(float((guess[hold_y == k] == k).mean()), 3) for k, c in enumerate(CLASSES) if (hold_y == k).any()}}
        print('holdout', json.dumps(metrics['holdout']))
    torch.save({'states': nets, 'mean': mean, 'spread': spread, 'classes': list(CLASSES), 'features': list(FEATURE_NAMES), 'hidden': HIDDEN}, out / 'model.pt')
    (out / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
