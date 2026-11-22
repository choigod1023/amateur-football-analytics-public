"""Compare ball paths (scripts/apply_ball_rerank.py) with the balls a person labelled and verified in the review store.

Usage: python scripts/evaluate_ball_paths.py <review store> <ball paths json> [--clips b37,b38,b39] [--radius 12]

For the frames labelled "ball" (and not rejected in the verification tab): right = the path answered within `radius` px, wrong = it answered somewhere else,
missed = it did not answer. For the frames labelled "none": false = the path answered anyway. Also reported: how many labelled balls had a candidate circle within
`radius` px at all (a ball that no candidate covers cannot be found by the re-ranker, however good it is), and how many were in frames the path answered with an
unmoving point (a point that stays within 3 px for 1.5 s or more is a static object, not a flying ball).
"""
import argparse
import json
import math
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('paths')
    parser.add_argument('--clips')
    parser.add_argument('--radius', type=float, default=12.0)
    args = parser.parse_args()
    root = Path(args.store) / 'ball'
    paths = json.loads(Path(args.paths).read_text(encoding='utf-8'))
    wanted = set(args.clips.split(',')) if args.clips else set(paths)
    total = {'ball': 0, 'right': 0, 'wrong': 0, 'missed': 0, 'candidate_covers': 0, 'none': 0, 'false': 0}
    for clip in sorted(wanted):
        if clip not in paths:
            continue
        labels = json.loads((root / 'labels' / f'{clip}.json').read_text(encoding='utf-8'))
        cands = {e['file']: e['cands'] for e in json.loads((root / 'clips' / clip / 'candidates.json').read_text(encoding='utf-8'))['frames']}
        answer = paths[clip]['path']
        row = {k: 0 for k in total}
        for name, label in labels.items():
            if label.get('state') == 'ball' and label.get('verified') != 'rejected':
                row['ball'] += 1
                if any(math.hypot(c[0] - label['x'], c[1] - label['y']) <= args.radius for c in cands.get(name, [])):
                    row['candidate_covers'] += 1
                if name in answer:
                    row['right' if math.hypot(answer[name][0] - label['x'], answer[name][1] - label['y']) <= args.radius else 'wrong'] += 1
                else:
                    row['missed'] += 1
            elif label.get('state') == 'none':
                row['none'] += 1
                row['false'] += name in answer
        for k in total:
            total[k] += row[k]
        print(clip, row)
    b = max(1, total['ball'])
    print('all', total)
    print(f"balls found right {total['right'] / b:.0%}, wrong place {total['wrong'] / b:.0%}, not answered {total['missed'] / b:.0%}; a candidate covered {total['candidate_covers'] / b:.0%} of the labelled balls; "
          f"answered in {total['false']} of {total['none']} frames labelled no ball")


if __name__ == '__main__':
    main()
