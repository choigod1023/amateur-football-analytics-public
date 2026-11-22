"""Compare pseudo-labelled shirt prototypes against existing cluster centroids.

Research only: frame labels are used to score and map anonymous groups only.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.team_suggestions import TeamSuggestions, shirt_histogram
from app.tiled_tracking import TiledPlayerTracker
from scripts.evaluate_wide_team_gt import scan
from scripts.evaluate_wide_team_detected import match


def classify(feature, prototypes, max_distance, margin=.15):
    if feature is None or not all(len(x) for x in prototypes):
        return None
    # Use closest sample per class; no class inference for ambiguous examples.
    distances = np.array([np.linalg.norm(p-feature, axis=1).min() for p in prototypes])
    if distances.min() > max_distance or (distances.max()-distances.min()) / max(distances.max(), 1e-9) < margin:
        return None
    return int(np.argmin(distances))


def run(folder, weights, frames):
    torch.set_num_threads(2)
    model = YOLO(str(weights)); tracker = TiledPlayerTracker(model, 'cpu', 640, .95)
    group = TeamSuggestions(); samples = collections.defaultdict(list); votes = collections.Counter()
    bootstrap = []
    for frame, gt, truth in scan(folder, '0000_0030', range(1, 11)):
        tracks = tracker.update(frame); group.update(frame, tracks); matched, _ = match(tracks, gt, truth)
        for i, (box, tid) in enumerate(tracks):
            feat = shirt_histogram(frame, box)
            if feat is not None:
                samples[tid].append(feat)
                if i in matched: bootstrap.append((feat, matched[i]))
    if group.centres is None: raise ValueError('unlabelled bootstrap did not fit')
    for feat, truth in bootstrap:
        prediction = group._classify(feat)
        if prediction is not None: votes[prediction, truth] += 1
    direct = votes[0, 0] + votes[1, 1]; flipped = votes[0, 1] + votes[1, 0]
    if direct == flipped: raise ValueError('ambiguous label mapping')
    permutation = int(flipped > direct)
    prototypes = [[], []]
    for values in samples.values():
        feature = np.median(np.stack(values), axis=0)
        pseudo_label = group._classify(feature)
        if pseudo_label is not None: prototypes[pseudo_label].append(feature)
    prototypes = [np.asarray(x, dtype=float).reshape(-1, 16) for x in prototypes]
    results = {}
    for segment in ('0060_0090', '0120_0150'):
        tracker = TiledPlayerTracker(model, 'cpu', 640, .95)
        counts = collections.defaultdict(collections.Counter)
        for frame, gt, truth in scan(folder, segment, range(101, 101+frames)):
            tracks = tracker.update(frame); matched, missing = match(tracks, gt, truth)
            for name in ('baseline', 'nearest_020', 'nearest_030', 'nearest_040'):
                counts[name]['gt_unmatched'] += missing
            for i, (box, tid) in enumerate(tracks):
                feature = shirt_histogram(frame, box)
                predictions = {'baseline': group._classify(feature), **{f'nearest_{int(d*100):03}': classify(feature, prototypes, d) for d in (.2,.3,.4)}}
                for name, prediction in predictions.items():
                    c = counts[name]
                    if i not in matched:
                        c['unmatched_detection'] += 1; c['unmatched_assigned'] += int(prediction is not None)
                    else:
                        c['matched'] += 1
                        c['unknown' if prediction is None else 'correct' if prediction ^ permutation == matched[i] else 'wrong'] += 1
        results[segment] = {k: dict(v) for k,v in counts.items()}
    return {'frames_per_segment':frames, 'prototype_counts':[len(p) for p in prototypes], 'votes':{str(k):v for k,v in votes.items()},'results':results}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path); p.add_argument('weights', type=Path)
    p.add_argument('--frames', type=int, default=30)
    a = p.parse_args()
    if a.frames < 1: p.error('frames must be positive')
    print(json.dumps(run(a.folder, a.weights, a.frames), indent=2))
