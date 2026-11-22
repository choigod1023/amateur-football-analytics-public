"""Audit temporal shirt features with real detector boxes and tracker IDs.

Research only: the first ten frames' labels map arbitrary unsupervised group
numbers for scoring, not training; no tactical/role labels are inferred.
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


def smoothed_predictions(group, feature, tid, frame_num, histories):
    predictions = {'baseline': group._classify(feature)}
    for kind, history in histories.items():
        previous = history.get(tid)
        if feature is None:
            predictions[kind] = None
            continue
        values = ([feature] if previous is None or frame_num - previous[0] > 3
                  else (previous[1] + [feature])[-(3 if kind == 'window3' else 8):])
        history[tid] = (frame_num, values)
        if kind == 'window3':
            aggregate = np.mean(values, axis=0)
        else:
            alpha = .3 if kind == 'ema3' else .7
            aggregate = values[0]
            for value in values[1:]:
                aggregate = (1 - alpha) * aggregate + alpha * value
        predictions[kind] = group._classify(aggregate)
    return predictions


def run(folder, weights, start, length, device, confidence):
    torch.set_num_threads(2)
    model = YOLO(str(weights))
    tracker = TiledPlayerTracker(model, device, 640, confidence)
    group = TeamSuggestions()
    initial = []
    for frame, gt, truth in scan(folder, '0000_0030', range(1, 11)):
        tracks = tracker.update(frame)
        group.update(frame, tracks)
        matched, _ = match(tracks, gt, truth)
        initial.extend((shirt_histogram(frame, box), matched[i])
                       for i, (box, _) in enumerate(tracks) if i in matched)
    if group.centres is None:
        raise ValueError('Unlabelled bootstrap failed')
    votes = collections.Counter((group._classify(f), team) for f, team in initial
                                if group._classify(f) is not None)
    direct, flipped = votes[0, 0] + votes[1, 1], votes[0, 1] + votes[1, 0]
    if direct == flipped:
        raise ValueError('Cannot map labels for scoring')
    permutation = int(flipped > direct)
    results = {}
    for segment in ('0060_0090', '0120_0150'):
        tracker = TiledPlayerTracker(model, device, 640, confidence)
        histories = {key: {} for key in ('ema3', 'ema7', 'window3')}
        counts = collections.defaultdict(collections.Counter)
        for n, (frame, gt, truth) in enumerate(scan(folder, segment, range(start, start + length))):
            tracks = tracker.update(frame)
            matched, missing = match(tracks, gt, truth)
            for c in ('baseline', *histories):
                counts[c]['gt_unmatched'] += missing
            for i, (box, tid) in enumerate(tracks):
                feature = shirt_histogram(frame, box)
                predictions = smoothed_predictions(group, feature, tid, n, histories)
                for kind, prediction in predictions.items():
                    c = counts[kind]
                    if i not in matched:
                        c['unmatched_detection'] += 1
                        c['unmatched_assigned'] += int(prediction is not None)
                    else:
                        c['matched'] += 1
                        key = ('unknown' if prediction is None else
                               'correct' if prediction ^ permutation == matched[i] else 'wrong')
                        c[key] += 1
        results[segment] = {kind: dict(value) for kind, value in counts.items()}
    return {'start': start, 'frames_each': length, 'confidence': confidence,
            'bootstrap_votes': {str(k): v for k, v in votes.items()},
            'results': results,
            'limitations': 'Same previously used game/camera, correlated observations; GT only maps groups and scores IoU>=0.5, unmatched may contain referees or unlabelled players. No role, home/away or true live accuracy evaluation.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('weights', type=Path)
    p.add_argument('--start', type=int, default=101)
    p.add_argument('--frames', type=int, default=80)
    p.add_argument('--device', default='cpu')
    p.add_argument('--confidence', type=float, default=.95)
    a = p.parse_args()
    if a.start < 1 or a.frames < 1 or not 0 < a.confidence <= 1:
        p.error('Invalid start, frame count or confidence')
    print(json.dumps(run(a.folder, a.weights, a.start, a.frames, a.device, a.confidence), indent=2))
