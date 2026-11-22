"""Tactical report of a stretch of tracked play: missing players placed at estimated positions, team lines, open passing
lanes, breakthrough runs and plain-language feedback per window.

Usage: python scripts/build_tactical_report.py <tracks.json from track_from_cache.py> <calibrations.json> <camera> <output folder>
       [--pitch-length 89 --pitch-width 62] [--reference-bg A B TX TY] [--shift-schedule "0:0,0;1950:0.3,0.3"]
       [--direction-a 1] [--window 60] [--from-second S] [--to-second E]

Writes report.md (Korean) and tactical.json. --direction-a is the way team A attacks along the pitch length (+1 toward
+x, -1 toward -x; team B attacks the other way); it flips at half time. There is no ball in this data, so the report
says where lanes were open and who ran past a defender, not who passed or dribbled. Estimated players are guesses and
are counted separately in every number.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.pitch_map import feet_to_metres, fit  # noqa: E402
import team_profile_cli  # noqa: E402
from app.team_style import short_name  # noqa: E402
from app.tactical_feedback import breakthrough_runs, estimate_missing, feedback, open_lanes, team_lines  # noqa: E402
from build_team_minimap import parse_schedule, shift_at  # noqa: E402

REMEMBER_FRAMES = 50          # a player lost for longer than this (10 s) is no longer carried along


def clock(seconds):
    seconds = int(seconds)
    return f'{seconds // 60}:{seconds % 60:02d}'


def metre_rows(tracks, fitted, schedule, bg, first_frame, last_frame, width=1920, height=1080, *, include_estimates=False, evidence=None):
    """{frame: {team: [(track, x, y)]}} and {track: [(frame, x, y)]} for team A, B players that stand on the pitch."""
    by_frame, paths = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    for tid, rows in tracks.items():
        for row in rows:
            if row['team'] not in ('A', 'B') or not first_frame <= row['frame'] < last_frame:
                continue
            estimated = bool(row.get('interpolated') or row.get('predicted') or row.get('estimated'))
            if evidence is not None:
                key = 'estimated_rows' if estimated else 'observed_rows'
                evidence[key] = evidence.get(key, 0) + 1
            if estimated and not include_estimates:
                continue
            m = feet_to_metres(fitted, row['box'], width, height, shift_at(schedule, row['frame']), bg)
            if m is None:
                continue
            by_frame[row['frame']][row['team']].append((tid, m[0], m[1]))
            paths[tid].append((row['frame'], m[0], m[1]))
    for rows in paths.values():
        rows.sort()
    return by_frame, paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('tracks')
    parser.add_argument('calibrations')
    parser.add_argument('camera')
    parser.add_argument('output')
    parser.add_argument('--pitch-length', type=float)
    parser.add_argument('--pitch-width', type=float)
    parser.add_argument('--reference-bg', type=float, nargs=4, metavar=('A', 'B', 'TX', 'TY'))
    parser.add_argument('--shift-schedule')
    parser.add_argument('--direction-a', type=int, choices=(1, -1), default=1)
    parser.add_argument('--window', type=int, default=60, help='seconds per report window')
    parser.add_argument('--video', action='store_true', help='also draw minimap.mp4: seen players, estimated players, open forward lanes, lines, breakthrough runs and the feedback of the current window')
    parser.add_argument('--from-second', type=float, help='video time where the report starts (default: start of the tracks)')
    parser.add_argument('--to-second', type=float)
    team_profile_cli.add_argument(parser)
    args = parser.parse_args()
    team_profile_cli.setup(args)
    result = json.loads(Path(args.tracks).read_text(encoding='utf-8'))
    record = json.loads(Path(args.calibrations).read_text(encoding='utf-8')).get(args.camera)
    if not record:
        raise SystemExit(f'No saved calibration for {args.camera}.')
    override = {k: v for k, v in (('length', args.pitch_length), ('width', args.pitch_width)) if v}
    if override:
        record = {**record, 'pitch': {**(record.get('pitch') or {}), **override}}
    fitted = fit(record)
    if 'H' not in fitted:
        raise SystemExit('Calibration refused: ' + fitted['error'])
    fps, offset = float(result['fps']), float(result['first_second'])
    first = 0 if args.from_second is None else max(0, int(round((args.from_second - offset) * fps)))
    last = result['frames'] if args.to_second is None else min(result['frames'], int(round((args.to_second - offset) * fps)))
    schedule = parse_schedule(args.shift_schedule) if args.shift_schedule else []
    by_frame, paths = metre_rows(result['tracks'], fitted, schedule, tuple(args.reference_bg) if args.reference_bg else None, first, last)
    pitch = fitted['pitch']
    direction = {'A': args.direction_a, 'B': -args.direction_a}
    window_frames = int(args.window * fps)
    seen_last, windows = {}, defaultdict(lambda: {'A': defaultdict(list), 'B': defaultdict(list)})
    centres = {}
    drawn = defaultdict(dict)
    for frame in range(first, last):
        placed = by_frame.get(frame, {})
        for team in ('A', 'B'):
            members = placed.get(team, [])
            if members:
                centres[(frame, team)] = (sum(m[1] for m in members) / len(members), sum(m[2] for m in members) / len(members))
            for tid, x, y in members:
                seen_last[tid] = (frame, x, y, team)
        if (not args.video and (frame - first) % int(fps)) or not placed.get('A') or not placed.get('B'):
            continue
        slot = windows[(frame - first) // window_frames]
        points = {}
        for team in ('A', 'B'):
            members = placed[team]
            now = {tid for tid, _, _ in members}
            centre = centres[(frame, team)]
            recent = []
            for tid, (seen_at, x, y, owner) in sorted(seen_last.items(), key=lambda kv: -kv[1][0]):
                if owner != team or tid in now or not 0 < frame - seen_at <= REMEMBER_FRAMES:
                    continue
                before = centres.get((seen_at, team), centre)
                recent.append((x, y, (frame - seen_at) / fps))
                recent[-1] = (x + (centre[0] - before[0]), y + (centre[1] - before[1]), recent[-1][2])
            seen_xy = [(x, y) for _, x, y in members]
            guesses = estimate_missing(seen_xy, [(x, y, a) for x, y, a in recent], pitch)
            points[team] = (seen_xy, [(g['x'], g['y']) for g in guesses], guesses)
        for team, other in (('A', 'B'), ('B', 'A')):
            seen_xy, guess_xy, guesses = points[team]
            everyone = seen_xy + guess_xy
            lanes = open_lanes(everyone, points[other][0] + points[other][1], direction[team])
            slot[team]['seen'].append(len(seen_xy))
            slot[team]['estimated'].append(len(guess_xy))
            slot[team]['open'].append(len(lanes))
            slot[team]['forward_open'].append(sum(1 for l in lanes if l['forward']))
            slot[team]['possible'].append(sum(1 for i, a in enumerate(everyone) for j, b in enumerate(everyone) if i != j and 6.0 <= ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 <= 35.0))
            lines = team_lines(everyone, direction[team])
            drawn[frame][team] = {'seen': seen_xy, 'guesses': guesses, 'lanes': [l for l in lanes if l['forward']], 'everyone': everyone, 'lines': lines}
            if lines:
                for key in ('defence', 'midfield', 'attack', 'defence_to_midfield', 'midfield_to_attack'):
                    slot[team][key].append(lines[key])
            slot[team]['guess_kinds'].append(sum(1 for g in guesses if g['kind'] == 'gap'))
    team_of = {tid: seen_last[tid][3] for tid in paths}
    other_points = lambda team: (lambda frame: [(x, y) for _, x, y in by_frame.get(frame, {}).get('B' if team == 'A' else 'A', [])])
    runs = []
    for tid, path in paths.items():
        if len(path) < 15:
            continue
        for run in breakthrough_runs(path, other_points(team_of[tid]), direction[team_of[tid]], fps):
            runs.append({**run, 'track': tid, 'team': team_of[tid]})
    runs.sort(key=lambda r: r['frame'])
    mean = lambda values: sum(values) / len(values) if values else 0.0
    lines_md = [f'# 전술 관찰 보고서 ({clock(offset + first / fps)} ~ {clock(offset + last / fps)})', '',
                f'- 카메라 {args.camera}, 경기장 크기 가정 {pitch["length"]:.0f}m x {pitch["width"]:.0f}m, 보정 오차 {fitted["rms"]:.2f}m',
                f'- {short_name("A")} 공격 방향: {"+x" if args.direction_a == 1 else "-x"} ({short_name("B")}는 반대 방향)',
                '- 공 정보가 없으므로 패스, 드리블, 개인 돌파 능력은 판정하지 않고, 열린 패스길과 상대 수비를 넘어서는 달리기만 보고합니다.',
                '- 추정 선수는 최근에 보였던 위치나 팀 대형의 빈 곳에 채운 값이므로 실제 위치가 아닙니다.', '']
    usual = {}
    for team in ('A', 'B'):
        pooled = defaultdict(list)
        for index in windows:
            for key, values in windows[index][team].items():
                pooled[key].extend(values)
        if len(pooled['seen']) >= 5 and pooled['defence']:
            usual[team] = {'lines': {k: mean(pooled[k]) for k in ('defence', 'midfield', 'attack', 'defence_to_midfield', 'midfield_to_attack')},
                           'lanes': {'open': mean(pooled['open']), 'forward_open': mean(pooled['forward_open']), 'possible': mean(pooled['possible'])}}
    summary = {}
    for index in sorted(windows):
        start = offset + (first + index * window_frames) / fps
        lines_md.append(f'## {clock(start)} ~ {clock(start + args.window)}')
        for team in ('A', 'B'):
            w = windows[index][team]
            if len(w['seen']) < 5:
                continue
            lines = {k: mean(w[k]) for k in ('defence', 'midfield', 'attack', 'defence_to_midfield', 'midfield_to_attack')} if w['defence'] else None
            lanes = {'open': mean(w['open']), 'forward_open': mean(w['forward_open']), 'possible': mean(w['possible'])}
            notes = feedback(team, mean(w['seen']), mean(w['estimated']), lines, lanes, usual.get(team))
            summary[f'{index}:{team}'] = {'seen': round(mean(w['seen']), 1), 'estimated': round(mean(w['estimated']), 1), 'lines': lines, 'lanes': lanes, 'notes': notes}
            lines_md.extend(f'- {note}' for note in notes)
        mine = [r for r in runs if start <= offset + r['frame'] / fps < start + args.window]
        for r in mine[:5]:
            lines_md.append(f'- {short_name(r["team"])}의 선수(추적 {r["track"]})가 {clock(offset + r["frame"] / fps)}에 시속 {r["speed"] * 3.6:.0f}km 안팎으로 전진하며 수비 {r["beaten"]}명을 제쳤습니다(공 소유는 확인되지 않음).')
        lines_md.append('')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if args.video:
        from tactical_draw import render
        render(out / 'minimap.mp4', drawn, runs, summary, pitch, first, last, fps, offset, window_frames, direction, clock)
    (out / 'report.md').write_text('\n'.join(lines_md), encoding='utf-8')
    (out / 'tactical.json').write_text(json.dumps({'windows': summary, 'runs': runs}, ensure_ascii=False, indent=1), encoding='utf-8')
    print('wrote', out / 'report.md', '| windows', len(summary), '| runs', len(runs))


if __name__ == '__main__':
    main()
