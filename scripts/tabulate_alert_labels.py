"""Count the human judgements of the alert sessions per session and per alert kind, with 95 % Wilson intervals (read only).

python scripts/tabulate_alert_labels.py [<store>] [--sessions gk2-h1,gk2-h2]

Reads <store>/alerts/<session>/alerts.jsonl and <store>/alerts/labels/<session>-<n>.json (labels ok, wrong, useless). 'wrong' and 'useless' both count as a wrong alert.
Sessions that have no alerts.jsonl any more (replay-h2) are counted per session only, without kinds. Human judgements are only counted here, never changed.
"""
import argparse
import collections
import glob
import json
import re
from math import sqrt
from pathlib import Path

WORK = Path(__file__).resolve().parents[3] / 'work'
STORE = WORK / 'human-labels' / 'public-own-match-review-20261111'


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - a) / d, (c + a) / d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store', nargs='?', default=str(STORE))
    parser.add_argument('--sessions', default='gk2-h1,gk2-h2')
    args = parser.parse_args()
    alerts = Path(args.store) / 'alerts'
    labels = {}
    for f in glob.glob(str(alerts / 'labels' / '*.json')):
        d = json.loads(Path(f).read_text(encoding='utf-8'))
        labels[d['id']] = d['label']
    per_kind = collections.defaultdict(lambda: [0, 0])      # kind -> [wrong, judged]
    for session in args.sessions.split(','):
        rows = [json.loads(x) for x in (alerts / session / 'alerts.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
        judged = [(r['kind'], labels[f'{session}-{i}']) for i, r in enumerate(rows) if f'{session}-{i}' in labels]
        wrong = sum(1 for _, l in judged if l != 'ok')
        lo, hi = wilson(wrong, len(judged))
        print(f'{session}: alerts {len(rows)}, judged {len(judged)}, wrong or useless {wrong} ({wrong / max(1, len(judged)):.0%}, 95% {lo:.0%}-{hi:.0%})')
        for kind, label in judged:
            per_kind[kind][1] += 1
            per_kind[kind][0] += label != 'ok'
    print('per kind (all sessions together):')
    for kind, (wrong, n) in sorted(per_kind.items()):
        lo, hi = wilson(wrong, n)
        print(f'  {kind:14s} wrong {wrong}/{n} ({wrong / n:.0%}, 95% {lo:.0%}-{hi:.0%}){"  <- fewer than 20 judged: reference only" if n < 20 else ""}')
    other = collections.Counter(re.sub(r'-\d+$', '', k) for k in labels if not any(k.startswith(s + '-') for s in args.sessions.split(',')))
    print('other sessions with judgements:', dict(other))


if __name__ == '__main__':
    main()
