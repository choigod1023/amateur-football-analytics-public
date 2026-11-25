"""Put the positions and alerts of two analysed halves (two offline runs of scripts/run_live_feedback.py) into one session folder of the review store,
so that the half-time report service can make the report of both halves from them (/halftime?session=<name>, and half=2 of /api/v1/halftime/report).

python scripts/merge_halves_for_report.py --store <review store> --session final-1118 \
    --h1-positions positions_h1.jsonl --h1-alerts alerts_h1.jsonl --h2-positions positions_h2.jsonl --h2-alerts alerts_h2.jsonl \
    --h1-seconds 1320 --gap 300 [--h2-end 1500]

The second half starts at second (h1-seconds + gap) of the merged time line, with a {"type":"half"} line before it. Nothing in the inputs is changed; --h2-end drops the seconds of the second half after that
second of its own video (for instance a penalty shoot-out). The session folder must not exist yet.
"""
import argparse
import json
import sys
from pathlib import Path


def rows(path):
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.strip():
            try:
                yield json.loads(line)
            except ValueError:
                continue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--h1-positions', required=True)
    parser.add_argument('--h1-alerts', required=True)
    parser.add_argument('--h2-positions', required=True)
    parser.add_argument('--h2-alerts', required=True)
    parser.add_argument('--h1-seconds', type=float, required=True, help='length of the first half video')
    parser.add_argument('--gap', type=float, default=300.0, help='seconds between the two halves on the merged time line')
    parser.add_argument('--h2-end', type=float, help='last second of the second half video that is kept')
    args = parser.parse_args()
    folder = Path(args.store) / 'alerts' / args.session
    if folder.exists():
        sys.exit('The session folder exists already: ' + str(folder))
    offset = args.h1_seconds + args.gap
    keep = lambda t: args.h2_end is None or t <= args.h2_end
    positions, alerts = [], []
    for row in rows(args.h1_positions):
        positions.append(row)
    positions.append({'type': 'half', 'time': round(offset, 1), 'direction': next((r['direction'] for r in rows(args.h2_positions) if r.get('type') == 'header'), 1)})
    for row in rows(args.h2_positions):
        if row.get('type') == 'second' and keep(row['time']):
            positions.append({**row, 'time': round(row['time'] + offset, 1)})
    for row in rows(args.h1_alerts):
        alerts.append(row)
    for row in rows(args.h2_alerts):
        if isinstance(row.get('time'), (int, float)) and keep(row['time']):
            alerts.append({**row, 'time': round(row['time'] + offset, 1)})
    folder.mkdir(parents=True)
    (folder / 'positions.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in positions), encoding='utf-8')
    (folder / 'alerts.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in alerts), encoding='utf-8')
    print(f'{args.session}: {sum(1 for r in positions if r.get("type") == "second")} seconds of positions, {len(alerts)} alert rows, second half starts at {offset:.0f} s')


if __name__ == '__main__':
    main()
