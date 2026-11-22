"""Replay tracked positions of a recorded half through the live analyzer and measure it, so alert rules can be tuned without a live feed.

python scripts/replay_live_feedback.py <tracks.json> <calibrations.json> <camera> --direction -1 [--team B] [--reference-bg a b tx ty] [--shift-schedule S]
       [--goals 300,450,500] [--lead 20] [--alerts out.jsonl]

Prints the alerts per kind, and for every confirmed goal whether a box-attack or run alert came in the `lead` seconds before it (the share of goals the live
rules would have warned about), and how many alerts came outside any goal window (alerts of a kind that is good or bad by itself are not errors, but the numbers show how
busy the feed is: more than about two alerts a minute is too many for a coach).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.live_feedback import LiveAnalyzer  # noqa: E402
from app.pitch_map import fit  # noqa: E402
from build_tactical_report import clock, metre_rows  # noqa: E402
from build_team_minimap import parse_schedule  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('tracks')
    parser.add_argument('calibrations')
    parser.add_argument('camera')
    parser.add_argument('--direction', type=int, choices=(1, -1), required=True)
    parser.add_argument('--team', choices=('A', 'B'), default='B')
    parser.add_argument('--reference-bg', type=float, nargs=4)
    parser.add_argument('--shift-schedule')
    parser.add_argument('--pitch-length', type=float, default=89.0)
    parser.add_argument('--pitch-width', type=float, default=62.0)
    parser.add_argument('--goals', default='')
    parser.add_argument('--lead', type=float, default=20.0)
    parser.add_argument('--alerts')
    parser.add_argument('--cooldown', type=float, default=25.0)
    args = parser.parse_args()
    result = json.loads(Path(args.tracks).read_text(encoding='utf-8'))
    record = json.loads(Path(args.calibrations).read_text(encoding='utf-8'))[args.camera]
    fitted = fit({**record, 'pitch': {**(record.get('pitch') or {}), 'length': args.pitch_length, 'width': args.pitch_width}})
    schedule = parse_schedule(args.shift_schedule) if args.shift_schedule else []
    by_frame, _ = metre_rows(result['tracks'], fitted, schedule, tuple(args.reference_bg) if args.reference_bg else None, 0, result['frames'])
    fps, offset = float(result['fps']), float(result['first_second'])
    other = 'A' if args.team == 'B' else 'B'
    analyzer = LiveAnalyzer(args.direction, args.pitch_length, args.pitch_width, fps, args.cooldown)
    alerts = []
    for frame in range(result['frames']):
        teams = by_frame.get(frame, {})
        alerts += analyzer.update(offset + frame / fps, teams.get(args.team, []), teams.get(other, []))
    counts = {}
    for a in alerts:
        counts[a['kind']] = counts.get(a['kind'], 0) + 1
    minutes = result['frames'] / fps / 60
    print(f'{len(alerts)} alerts in {minutes:.1f} minutes ({len(alerts) / max(minutes, 1e-6):.2f} per minute):', counts)
    goals = [float(g) for g in args.goals.split(',') if g.strip()]
    warned = 0
    for goal in goals:
        before = [a for a in alerts if goal - args.lead <= a['time'] <= goal + 3 and a['kind'] in ('box_attack', 'run')]
        warned += bool(before)
        print(f'goal {clock(goal)}:', ', '.join(f"{a['kind']}@{clock(a['time'])}" for a in before) or 'no warning')
    if goals:
        print(f'goals with a box-attack or run alert in the {args.lead:.0f} s before: {warned} of {len(goals)}')
    if args.alerts:
        Path(args.alerts).write_text('\n'.join(json.dumps(a, ensure_ascii=False) for a in alerts), encoding='utf-8')


if __name__ == '__main__':
    main()
