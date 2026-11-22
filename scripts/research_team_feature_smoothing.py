"""Exploratory temporal shirt-feature smoothing on oracle boxes and IDs.

No labels train the feature or centres. The initial GT labels only map arbitrary
cluster numbers to the two evaluation labels; evaluation uses later frames.
These are correlated observations of one camera, not detector/tracker accuracy.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_wide_team_gt import scan
from app.team_suggestions import TeamSuggestions, shirt_histogram


def run(folder, start=101, frames=80):
    group = TeamSuggestions()
    initial = []
    for frame, tracks, truth in scan(folder, '0000_0030', range(1, 11)):
        group.update(frame, tracks)
        initial.extend((shirt_histogram(frame, box), truth[tid]) for box, tid in tracks)
    if group.centres is None:
        raise ValueError('Unlabelled bootstrap did not produce two groups')
    votes = collections.Counter((group._classify(f), t) for f, t in initial
                                if group._classify(f) is not None)
    direct = votes[0, 0] + votes[1, 1]
    flipped = votes[0, 1] + votes[1, 0]
    if direct == flipped:
        raise ValueError('Cannot map clusters to ground truth')
    permutation = int(flipped > direct)
    results = {}
    for segment in ('0060_0090', '0120_0150'):
        histories = {key: {} for key in ('ema3', 'ema7', 'window3')}
        counts = collections.defaultdict(collections.Counter)
        for n, (frame, tracks, truth) in enumerate(scan(folder, segment, range(start, start + frames))):
            for box, tid in tracks:
                feature = shirt_histogram(frame, box)
                predictions = {'baseline': group._classify(feature)}
                for kind, history in histories.items():
                    previous = history.get(tid)
                    if feature is None:
                        predictions[kind] = None
                        continue
                    values = ([feature] if previous is None or n - previous[0] > 3
                              else (previous[1] + [feature])[-(3 if kind == 'window3' else 8):])
                    history[tid] = (n, values)
                    if kind == 'window3':
                        aggregate = np.mean(values, axis=0)
                    else:
                        alpha = .3 if kind == 'ema3' else .7
                        aggregate = values[0]
                        for value in values[1:]:
                            aggregate = (1 - alpha) * aggregate + alpha * value
                    predictions[kind] = group._classify(aggregate)
                for kind, prediction in predictions.items():
                    outcome = ('unknown' if prediction is None else
                               'correct' if prediction ^ permutation == truth[tid] else 'wrong')
                    counts[kind][outcome] += 1
        results[segment] = {kind: dict(count) for kind, count in counts.items()}
    return {'frames_per_segment': frames, 'start_frame': start,
            'bootstrap_votes': {str(key): value for key, value in votes.items()},
            'permutation': permutation, 'results': results,
            'limitations': 'Oracle boxes and persistent ground-truth IDs; one game/camera; correlated frames; bootstrap GT only maps clusters; no role or unmatched detection evaluation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--start', type=int, default=101)
    parser.add_argument('--frames', type=int, default=80)
    args = parser.parse_args()
    if args.start < 1 or args.frames < 1:
        parser.error('start and frames must be positive')
    print(json.dumps(run(args.folder, args.start, args.frames), indent=2))
