"""Formation and space control of team B per five-minute window, from the tracks and the pitch calibration (positions only).

Usage: python scripts/formation_report.py <calibrations.json> <output json> --half "<name>|<tracks.json>|<camera>|<direction>|<offset>|<bg a,b,tx,ty>|<schedule>|<goals>" ... [--team B]
See app/team_formation.py for what the answers mean and do not mean.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import team_formation as tf, team_tactics as tt  # noqa: E402
from build_match_report import load_half  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('calibrations')
    parser.add_argument('output')
    parser.add_argument('--half', action='append', required=True)
    parser.add_argument('--team', default='B')
    args = parser.parse_args()
    calibrations = json.loads(Path(args.calibrations).read_text(encoding='utf-8'))
    other = 'A' if args.team == 'B' else 'B'
    result = []
    for spec in args.half:
        half = load_half(spec, calibrations, args.team)
        series = tt.seconds_series(half['by_frame'], args.team, other, half['direction'], half['fps'], half['result']['frames'])
        ours = tf.formation_summary(tf.formation_blocks(series, 'ours_points', 30))
        theirs = tf.formation_summary(tf.formation_blocks(series, 'theirs_points', 30))
        controls = tf.control_series(series, step=2)
        windows = tf.control_by_window(controls, 300)
        answered = sum(1 for r in series.values() if tf.formation(r['ours_points']))
        print(half['name'], 'seconds', len(series), 'with a formation answer', answered, 'with a control answer', len(controls))
        for (start, text, share, n, second), (_s, total, third, m) in zip(ours, windows):
            print(f'  {start // 60:>2}-{start // 60 + 5:<2} min  formation {text:<7} ({share * 100:3.0f}% of {n:2d} blocks of 30 s, next {second})  space {total * 100:4.1f}%  opponent third {third * 100:4.1f}%')
        result.append({'half': half['name'], 'ours_formation': [list(w) for w in ours], 'theirs_formation': [list(w) for w in theirs],
                       'control': [list(w) for w in windows], 'seconds_answered': answered})
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
