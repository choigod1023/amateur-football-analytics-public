"""Which of the alerts the coach judged does a rule variant keep? (research, read only)

python scripts/replay_judged_alerts.py <tracks.json> <calibrations.json> <camera> --direction 1 --session gk2-h2 [--reference-bg a b tx ty] [--shift-schedule S] [--output result.json]

The stored tracks of a half (the same input the judged alerts of the session were made from) are replayed through the variants of scripts/replay_frames_log.py. For every alert the
coach judged (labels ok / wrong / useless in <store>/alerts/labels/<session>-<n>.json) the script tells whether a variant gives an alert of the same kind within +-10 s. A good change keeps the
alerts judged ok and drops the ones judged wrong. The judgements are only read, never changed. The values of the variants were not chosen on these judgements, but any value read from them is
optimistic: new judgements are needed to confirm it. Alerts of the replay that the coach never saw are counted separately (they are neither right nor wrong).
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.pitch_map import fit  # noqa: E402
from build_tactical_report import metre_rows  # noqa: E402
from build_team_minimap import parse_schedule  # noqa: E402
import replay_frames_log as rf  # noqa: E402

STORE = Path(__file__).resolve().parents[3] / 'work' / 'human-labels' / 'public-own-match-review-20261111'


def judged(store, session):
    rows = [json.loads(line) for line in (store / 'alerts' / session / 'alerts.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    out = []
    for n, row in enumerate(rows):
        label_file = store / 'alerts' / 'labels' / f'{session}-{n}.json'
        if row.get('kind') in rf.SKIP or row.get('type') in rf.SKIP or not label_file.exists():
            continue
        label = json.loads(label_file.read_text(encoding='utf-8')).get('label')
        if label in ('ok', 'wrong', 'useless'):
            out.append({'n': n, 'kind': row['kind'], 'time': float(row['time']), 'label': 'right' if label == 'ok' else 'wrong'})
    return out, rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('tracks', type=Path); p.add_argument('calibrations', type=Path); p.add_argument('camera'); p.add_argument('--direction', type=int, choices=(1, -1), required=True)
    p.add_argument('--team', choices=('A', 'B'), default='B'); p.add_argument('--session', required=True); p.add_argument('--store', type=Path, default=STORE)
    p.add_argument('--reference-bg', type=float, nargs=4); p.add_argument('--shift-schedule'); p.add_argument('--pitch-length', type=float, default=89.0); p.add_argument('--pitch-width', type=float, default=62.0)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = json.loads(args.tracks.read_text(encoding='utf-8'))
    record = json.loads(args.calibrations.read_text(encoding='utf-8'))[args.camera]
    fitted = fit({**record, 'pitch': {**(record.get('pitch') or {}), 'length': args.pitch_length, 'width': args.pitch_width}})
    schedule = parse_schedule(args.shift_schedule) if args.shift_schedule else []
    by_frame, _ = metre_rows(result['tracks'], fitted, schedule, tuple(args.reference_bg) if args.reference_bg else None, 0, result['frames'])
    fps, offset = float(result['fps']), float(result['first_second'])
    other = 'A' if args.team == 'B' else 'B'
    rows = []
    for frame in range(result['frames']):
        teams = by_frame.get(frame, {})
        rows.append({'t': offset + frame / fps, 'team': teams.get(args.team, []), 'other': teams.get(other, [])})
    header = {'direction': args.direction, 'pitch_length': args.pitch_length, 'pitch_width': args.pitch_width, 'fps': fps}
    marks, session_rows = judged(args.store, args.session)
    out = {'session': args.session, 'judged': len(marks), 'judged_right': sum(1 for m in marks if m['label'] == 'right'), 'variants': {}}
    for name, setting in rf.VARIANTS.items():
        alerts = rf.replay(header, rows, setting)
        kinds = {}
        for m in marks:
            hit = any(k == m['kind'] and abs(t - m['time']) <= rf.WINDOW for k, t in alerts)
            row = kinds.setdefault(m['kind'], {'right': 0, 'right_kept': 0, 'wrong': 0, 'wrong_kept': 0})
            row[m['label']] += 1
            row[m['label'] + '_kept'] += int(hit)
        seen = sum(1 for k, t in alerts if any(k == m['kind'] and abs(t - m['time']) <= rf.WINDOW for m in marks))
        out['variants'][name] = {'alerts': len(alerts), 'near_a_judged_alert': seen, 'not_judged': len(alerts) - seen, 'by_kind': kinds,
                                 'right_kept': sum(v['right_kept'] for v in kinds.values()), 'wrong_kept': sum(v['wrong_kept'] for v in kinds.values())}
    for name, v in out['variants'].items():
        print(f"{name:27s} alerts={v['alerts']:3d} right kept {v['right_kept']}/{out['judged_right']} wrong kept {v['wrong_kept']}/{out['judged'] - out['judged_right']} "
              + ' '.join(f"{k}:{c['right_kept']}/{c['right']}ok,{c['wrong_kept']}/{c['wrong']}wrong" for k, c in sorted(v['by_kind'].items())))
    if args.output:
        args.output.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
