"""Score the hard-frame rules on the file of scripts/hard_frames_measure.py (research, read only).

python scripts/hard_frames_score.py <measure.json> [--out score.json]

Positive frame: a frame with a human-confirmed box (95% of them are judged by IoU >= 0.3, same rule as scripts/bench_human_boxes.py) that this detector does NOT find.
Control frame: a random frame of the match away from every human frame. Nobody has looked at it, so some of its frames hide missed players too: the flag rate on controls
is a work load (how many frames the user would get), not a false alarm rate. Precision cannot be measured with this material; the table gives recall and the flag rate.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.hard_frames import judge  # noqa: E402

RULES = {
    'count_drop>=3': {'drop': 3}, 'count_drop>=4': {'drop': 4}, 'count_drop>=5': {'drop': 5}, 'count_drop>=6': {'drop': 6},
    'low_total<27': {'drop': 0, 'low_total': 27}, 'low_total<30': {'drop': 0, 'low_total': 30}, 'low_total<33': {'drop': 0, 'low_total': 33},
    'team_low<6': {'drop': 0, 'team_low': 6}, 'team_low<7': {'drop': 0, 'team_low': 7}, 'team_low<8': {'drop': 0, 'team_low': 8},
    'team_drop>=2': {'drop': 0, 'team_drop': 2}, 'team_drop>=3': {'drop': 0, 'team_drop': 3},
    'count_drop>=4 or team_low<7': {'drop': 4, 'team_low': 7},
}


def iou(a, b):
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    i = w * h
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def wilson(k, n):
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return (round(c - m, 2), round(c + m, 2))


def main():
    path = sys.argv[1]
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    out = {}
    for name in data['weights']:
        pos, neg, ctl = [], [], []
        for r in data['rows']:
            m = r['models'][name]
            hist = [(h['n'], h['dark']) for h in m['history']]
            last = m['last']
            if r['group'] == 'control':
                ctl.append((hist, last))
                continue
            missed = [b for b in r['human_boxes'] if not any(iou(b, d) >= 0.3 for d in last['boxes'])]
            (pos if missed else neg).append((hist, last))
        out[name] = {'positive_frames': len(pos), 'covered_human_frames': len(neg), 'control_frames': len(ctl), 'rules': {}}
        print(f'\n{name}: frames with a missed human box {len(pos)}, human frames fully found {len(neg)}, control frames {len(ctl)}')
        print(f'{"rule":32s} recall(pos)         fully-found flagged   control flagged')
        for rule, settings in RULES.items():
            def fire(item):
                hist, last = item
                return bool(judge(hist, last['n'], last['dark'], settings=settings))
            k, kn, kc = sum(map(fire, pos)), sum(map(fire, neg)), sum(map(fire, ctl))
            out[name]['rules'][rule] = {'recall': [k, len(pos)], 'fully_found_flagged': [kn, len(neg)], 'control_flagged': [kc, len(ctl)]}
            print(f'{rule:32s} {k:3d}/{len(pos):3d} {wilson(k, len(pos))}   {kn:3d}/{len(neg):3d}            {kc:3d}/{len(ctl):3d} ({100 * kc / max(1, len(ctl)):.0f}%)')
    if '--out' in sys.argv:
        Path(sys.argv[sys.argv.index('--out') + 1]).write_text(json.dumps(out, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
