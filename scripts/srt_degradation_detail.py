"""How detailed can the coaching stay when the feed gets worse? (reads the output folder of scripts/srt_degradation_alerts.py, read only)

python scripts/srt_degradation_detail.py <work dir of srt_degradation_alerts.py> --start <segment start second> --direction 1 [--output detail.json]

For every received profile the positions of the focus team (positions.jsonl, one line per second, metres) are compared second by second with the reference run on the file:
  level 1  team:  centre of the team along the pitch, and the whole length of the team (deepest to most advanced player)
  level 2  lines: height of the back line (the 3 deepest players after the goalkeeper), height of the front line (3 most advanced), the gap between them
  level 3  slots: players on the left and on the right side, and the width of the team
  level 4  person: not measured (the names are not tracked; see wiki/research-player-identity-and-labelling.md)
A level counts as kept when at least 80 % of the compared seconds are within its tolerance. The tolerances are proposals, chosen from the size of the rules in app/live_feedback.py, not measured need.
"""
import argparse, json
from pathlib import Path

TOLERANCE = {'team_centre_m': 3.0, 'team_length_m': 5.0, 'back_line_m': 3.0, 'front_line_m': 3.0, 'line_gap_m': 4.0, 'left_right_count': 1, 'width_m': 5.0}
LEVELS = {1: ('team_centre_m', 'team_length_m'), 2: ('back_line_m', 'front_line_m', 'line_gap_m'), 3: ('left_right_count', 'width_m')}
SHARE = 0.80


def read(path, offset):
    out = {}
    path = Path(path)
    if not path.exists():
        return out
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('type') == 'second':
            out[int(row['time'] + offset)] = [(p[1], p[2]) for p in row['team']]
    return out


def shape(players, direction):
    """Numbers of one second (x along the attack: larger = more advanced) or None when fewer than 8 players were placed."""
    if len(players) < 8:
        return None
    xs = sorted(x * direction for x, _ in players)
    ys = [y for _, y in players]
    back = xs[1:4]                                        # after the deepest player (the goalkeeper in most seconds)
    front = xs[-3:]
    return {'team_centre_m': sum(xs) / len(xs), 'team_length_m': xs[-1] - xs[0], 'back_line_m': sum(back) / 3, 'front_line_m': sum(front) / 3,
            'line_gap_m': sum(front) / 3 - sum(back) / 3, 'left_right_count': sum(1 for y in ys if y < 0) - sum(1 for y in ys if y >= 0), 'width_m': max(ys) - min(ys)}


def compare(reference, candidate, direction):
    stats = {key: [] for key in TOLERANCE}
    both = 0
    for second, ref_players in reference.items():
        cand_players = candidate.get(second)
        a, b = shape(ref_players, direction), shape(cand_players, direction) if cand_players is not None else None
        if a is None or b is None:
            continue
        both += 1
        for key in TOLERANCE:
            stats[key].append(abs(a[key] - b[key]))
    result = {'seconds_compared': both}
    for key, values in stats.items():
        if values:
            values.sort()
            result[key] = {'median_abs_difference': round(values[len(values) // 2], 2), 'p90_abs_difference': round(values[min(len(values) - 1, int(len(values) * 0.9))], 2),
                           'share_within_tolerance': round(sum(1 for v in values if v <= TOLERANCE[key]) / len(values), 3)}
    kept = 0
    for level in (1, 2, 3):
        if all(key in result and result[key]['share_within_tolerance'] >= SHARE for key in LEVELS[level]):
            kept = level
        else:
            break
    result['detail_level_kept'] = kept
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('work_dir', type=Path); p.add_argument('--start', type=float, required=True); p.add_argument('--direction', type=int, choices=(1, -1), required=True)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    reference = read(args.work_dir / 'reference' / 'positions.jsonl', 0.0)
    out = {'tolerances': TOLERANCE, 'required_share': SHARE, 'profiles': {}}
    for folder in sorted(d for d in args.work_dir.iterdir() if d.is_dir() and d.name != 'reference'):
        candidate = read(folder / 'positions.jsonl', args.start)
        if candidate:
            out['profiles'][folder.name] = compare(reference, candidate, args.direction)
    for name, row in out['profiles'].items():
        cells = ' '.join(f"{k}={row[k]['share_within_tolerance']:.2f}" for k in TOLERANCE if k in row)
        print(f"{name:14s} level_kept={row['detail_level_kept']} seconds={row['seconds_compared']} {cells}")
    if args.output:
        args.output.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
