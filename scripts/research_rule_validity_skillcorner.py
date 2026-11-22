"""Same test as research_rule_validity.py on the SkillCorner open data (10 A-League matches, 10 Hz broadcast tracking), research only, read only.

python scripts/research_rule_validity_skillcorner.py <skillcorner data folder> [--window 30] [--matches all|id,id] [--cache folder] [--workers 8] [--out result.json]

Per match: tracking_extrapolated.jsonl (x, y in metres, pitch centre = 0, 10 Hz, thinned to 5 Hz), match.json (player -> team, pitch size), dynamic_events.csv.
A shot is a player_possession event whose end_type is 'shot' (time = frame_start / 10). The attack direction of a team in a period comes from the events' attacking_side.
Each team and period is replayed through LiveAnalyzer (production thresholds, no alert kind switched off) and scored exactly as in research_rule_validity.py:
attack alerts (box_attack, run, isolated) against the team's own shots, defence alerts (conceded_run, line_drop, gap_wide) against the opponent's shots, lift = rate after alerts / rate at every second.
Limits: extrapolated positions of players outside the broadcast view, pitch 105 x 68 and professional play, alerts of one kind correlated in time.
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.live_feedback import LiveAnalyzer  # noqa: E402
from research_rule_validity import ATTACK, DEFENCE, binom_p  # noqa: E402

FPS = 10
STEP = 2                      # 10 Hz -> 5 Hz


def read_match(folder):
    folder = Path(folder)
    mid = folder.name
    info = json.loads((folder / f'{mid}_match.json').read_text(encoding='utf-8'))
    team_of = {p['id']: p['team_id'] for p in info['players']}
    teams = (info['home_team']['id'], info['away_team']['id'])
    shots = {t: [] for t in teams}
    direction = {}
    with open(folder / f'{mid}_dynamic_events.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            team = int(r['team_id']) if r['team_id'] else None
            if team not in shots:
                continue
            period = int(r['period']) if r['period'] else None
            if period and r['attacking_side']:
                direction[(team, period)] = 1 if r['attacking_side'] == 'left_to_right' else -1
            if r['event_type'] == 'player_possession' and r['end_type'] == 'shot':
                shots[team].append(int(r['frame_start']) / FPS)
    frames = {}                  # period -> [(time, {team: [(player, x, y)]})]
    with open(folder / f'{mid}_tracking_extrapolated.jsonl', encoding='utf-8') as f:
        for line in f:
            d = json.loads(line)
            if d['period'] is None or d['frame'] % STEP:
                continue
            per_team = {t: [] for t in teams}
            for p in d['player_data']:
                team = team_of.get(p['player_id'])
                if team in per_team and p['x'] is not None:
                    per_team[team].append((p['player_id'], float(p['x']), float(p['y'])))
            frames.setdefault(d['period'], []).append((d['frame'] / FPS, per_team))
    return teams, shots, direction, frames, float(info['pitch_length']), float(info['pitch_width'])


def alerts_of(frames, direction, team, other, length, width):
    out = []
    for period, rows in frames.items():
        if (team, period) not in direction:
            continue
        analyzer = LiveAnalyzer(direction[(team, period)], length, width, fps=5.0, disabled=())
        t0 = rows[0][0]
        for t, per_team in rows:
            for a in analyzer.update(t - t0, per_team[team], per_team[other]):
                out.append({'kind': a['kind'], 'time': t0 + a['time']})
    return out


def load_match(args):
    """-> (teams, shots, {team: alerts}, {period: [(first time, last time)]}); the alerts are cached, so another window needs no replay."""
    folder, cache = args
    teams, shots, direction, frames, length, width = read_match(folder)
    spans = {p: [(rows[0][0], rows[-1][0])] for p, rows in frames.items()}
    file = Path(cache) / (Path(folder).name + '.json') if cache else None
    if file is not None and file.exists():
        alerts = {int(k): v for k, v in json.loads(file.read_text(encoding='utf-8')).items()}
    else:
        alerts = {team: alerts_of(frames, direction, team, other, length, width) for team, other in ((teams[0], teams[1]), (teams[1], teams[0]))}
        if file is not None:
            file.write_text(json.dumps(alerts), encoding='utf-8')
    return teams, shots, alerts, spans


def baseline(frames, shots, window):
    hits = total = 0
    for spans in frames.values():
        t0, t1 = spans[0]
        t = t0
        while t < t1 - window:
            total += 1
            hits += any(t < s <= t + window for s in shots)
            t += 1.0
    return hits, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder')
    parser.add_argument('--window', type=float, default=30.0)
    parser.add_argument('--matches', default='all')
    parser.add_argument('--out')
    parser.add_argument('--cache', help='folder for the replayed alerts of each match (a second window then takes seconds)')
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    root = Path(args.folder) / 'data' / 'matches'
    ids = sorted(p.name for p in root.iterdir() if p.is_dir()) if args.matches == 'all' else args.matches.split(',')
    stats, n_shots = {}, 0
    cache = Path(args.cache) if args.cache else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=min(len(ids), args.workers)) as pool:       # one match per process: the replay of one match is the slow part
        loaded = list(pool.map(load_match, [(str(root / mid), str(cache) if cache else None) for mid in ids]))
    for mid, (teams, shots, per_team_alerts, frames_info) in zip(ids, loaded):
        n_shots += sum(len(v) for v in shots.values())
        print(mid, 'shots', {t: len(v) for t, v in shots.items()}, flush=True)
        for team, other in ((teams[0], teams[1]), (teams[1], teams[0])):
            alerts = per_team_alerts[team]
            for kinds, mine in ((ATTACK, shots[team]), (DEFENCE, shots[other])):
                base_hit, base_total = baseline(frames_info, mine, args.window)
                for kind in kinds:
                    mine_alerts = [a for a in alerts if a['kind'] == kind]
                    s = stats.setdefault(kind, {'n': 0, 'pos': 0, 'base_hit': 0, 'base_total': 0, 'per_match': {}})
                    pos = sum(any(a['time'] < x <= a['time'] + args.window for x in mine) for a in mine_alerts)
                    s['n'] += len(mine_alerts)
                    s['pos'] += pos
                    s['base_hit'] += base_hit * len(mine_alerts)
                    s['base_total'] += base_total * len(mine_alerts)
                    pm = s['per_match'].setdefault(mid, [0, 0])
                    pm[0] += len(mine_alerts)
                    pm[1] += pos
    print(f'window {args.window:.0f} s, {len(ids)} matches, {n_shots} shots')
    result = {}
    for kind in ATTACK + DEFENCE:
        s = stats.get(kind)
        if not s or not s['n']:
            print(f'{kind:13s} no alerts')
            continue
        rate, base = s['pos'] / s['n'], s['base_hit'] / s['base_total']
        p = binom_p(s['pos'], s['n'], base)
        better = sum(1 for n, pos in s['per_match'].values() if n and pos / n > base)
        print(f'{kind:13s} alerts {s["n"]:4d}, followed by a shot {s["pos"]:4d} ({rate:.0%}), baseline {base:.0%}, lift {rate / base if base else float("nan"):.2f}, one-sided p {p:.3f}, '
              f'matches above baseline {better}/{sum(1 for n, _ in s["per_match"].values() if n)}')
        result[kind] = {'alerts': s['n'], 'positive': s['pos'], 'rate': rate, 'baseline': base, 'p': p, 'per_match': s['per_match']}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
