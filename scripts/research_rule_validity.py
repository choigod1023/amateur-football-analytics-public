"""Do our live alert rules point at anything real? Replay public tracking data through the live analyzer and compare with the shots that followed (research, read only).

python scripts/research_rule_validity.py <Metrica sample-data folder> [--window 30] [--games 1,2] [--out result.json]

For every game, team and period the analyzer (app/live_feedback.py, the same thresholds as in production) is fed the exact positions at 5 per second. Each alert is then scored against the events:
  * attack alerts (box_attack, run, isolated): positive when the alerted team takes a shot within <window> seconds after the alert,
  * defence alerts (conceded_run, line_drop, gap_wide): positive when the opponent takes a shot within <window> seconds.
Baseline: the same question asked at every second of the same team and period (shot of that team, or of the opponent, in the next <window> s). Lift = rate after alerts / baseline rate.
Only Metrica sample games 1 and 2 (CSV, pitch 105 x 68, normalised 0..1 positions at 25 Hz) are read; shots are the events of type SHOT (blocked, saved, goal, off target alike).
Limits: pitch 105 x 68 and professional play instead of our 89 x 62 amateur pitch, few shots (about 48 in two games) so every interval is wide, alerts of one kind are correlated in time,
and a shot soon after a box-attack alert is expected because the box attack is itself part of a shot sequence (it shows the rule is meaningful, not that it predicts the future).
"""
import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.live_feedback import LiveAnalyzer  # noqa: E402

LENGTH, WIDTH = 105.0, 68.0
ATTACK = ('box_attack', 'run', 'isolated')
DEFENCE = ('conceded_run', 'line_drop', 'gap_wide')
STEP = 5                      # 25 Hz -> 5 Hz


def read_tracking(path):
    """-> (period array, time array, {player id: (x, y) arrays in metres centred on the pitch})"""
    with open(path, encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)
        ids = next(reader)
        head = next(reader)
        rows = [r for r in reader]
    period = np.array([int(r[0]) for r in rows])
    time = np.array([float(r[2]) for r in rows])
    players = {}
    for col in range(3, len(head) - 2, 2):
        name = head[col]
        if not name.startswith('Player'):
            continue
        x = np.array([float(r[col]) if r[col] not in ('', 'NaN') else np.nan for r in rows])
        y = np.array([float(r[col + 1]) if r[col + 1] not in ('', 'NaN') else np.nan for r in rows])
        players[name] = ((x - 0.5) * LENGTH, (y - 0.5) * WIDTH)
    return period, time, players


def read_shots(path):
    out = {'Home': [], 'Away': []}
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['Type'] == 'SHOT':
                out[r['Team']].append(float(r['Start Time [s]']))
    return out


def direction_of(players, rows):
    """+1 when the team attacks toward +x in the period that starts at the first row of <rows>: it stands in the other half at kick-off."""
    xs = [p[0][rows[0]] for p in players.values() if not np.isnan(p[0][rows[0]])]
    return 1 if np.mean(xs) < 0 else -1


def run_team(period, time, own, other, kind_filter=None):
    alerts = []
    for p in sorted(set(period.tolist())):
        idx = np.where(period == p)[0]
        direction = direction_of(own, idx)
        analyzer = LiveAnalyzer(direction, LENGTH, WIDTH, fps=5.0, disabled=())
        for i in idx[::STEP]:
            team = [(n, float(x[i]), float(y[i])) for n, (x, y) in own.items() if not math.isnan(x[i])]
            opp = [(n, float(x[i]), float(y[i])) for n, (x, y) in other.items() if not math.isnan(x[i])]
            for a in analyzer.update(float(time[i] - time[idx[0]]), team, opp):
                alerts.append({'kind': a['kind'], 'time': float(time[idx[0]] + a['time']), 'period': int(p)})
    return alerts


def baseline(period, time, shots, window):
    """Share of seconds (per period) that are followed by a shot within <window> seconds."""
    hits = total = 0
    for p in sorted(set(period.tolist())):
        t0, t1 = time[period == p][0], time[period == p][-1]
        for t in np.arange(t0, t1 - window, 1.0):
            total += 1
            hits += any(t < s <= t + window for s in shots)
    return hits, total


def binom_p(k, n, p0):
    """One-sided probability of at least k hits in n draws at rate p0 (exact binomial; alerts are correlated in time, so read it as a rough guide only)."""
    if p0 <= 0 or p0 >= 1:
        return 1.0 if k <= 0 else 0.0
    log = lambda j: math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * math.log(p0) + (n - j) * math.log(1 - p0)      # log space: many alerts overflow floats
    return min(1.0, sum(math.exp(log(j)) for j in range(k, n + 1)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder')
    parser.add_argument('--window', type=float, default=30.0)
    parser.add_argument('--games', default='1,2')
    parser.add_argument('--out')
    args = parser.parse_args()
    folder = Path(args.folder) / 'data'
    stats = {}
    for g in args.games.split(','):
        base = folder / f'Sample_Game_{g}'
        period, time, home = read_tracking(base / f'Sample_Game_{g}_RawTrackingData_Home_Team.csv')
        _, _, away = read_tracking(base / f'Sample_Game_{g}_RawTrackingData_Away_Team.csv')
        shots = read_shots(base / f'Sample_Game_{g}_RawEventsData.csv')
        for team, own, other, opp_name in (('Home', home, away, 'Away'), ('Away', away, home, 'Home')):
            alerts = run_team(period, time, own, other)
            for kinds, mine in ((ATTACK, shots[team]), (DEFENCE, shots[opp_name])):
                base_hit, base_total = baseline(period, time, mine, args.window)
                for a in alerts:
                    if a['kind'] not in kinds:
                        continue
                    positive = any(a['time'] < s <= a['time'] + args.window for s in mine)
                    s = stats.setdefault(a['kind'], {'n': 0, 'pos': 0, 'base_hit': 0, 'base_total': 0, 'teams': set()})
                    s['n'] += 1
                    s['pos'] += positive
                    s['teams'].add((g, team))
                # baseline counts once per (game, team, kind group); weight it by the alerts of that group's kinds
                for kind in kinds:
                    n_k = sum(1 for a in alerts if a['kind'] == kind)
                    if n_k and kind in stats:
                        stats[kind]['base_hit'] += base_hit * n_k
                        stats[kind]['base_total'] += base_total * n_k
    print(f'window {args.window:.0f} s, games {args.games}')
    result = {}
    for kind in ATTACK + DEFENCE:
        s = stats.get(kind)
        if not s:
            print(f'{kind:13s} no alerts')
            continue
        rate, base = s['pos'] / s['n'], s['base_hit'] / s['base_total']
        p = binom_p(s['pos'], s['n'], base)
        print(f'{kind:13s} alerts {s["n"]:3d}, followed by a shot {s["pos"]:3d} ({rate:.0%}), baseline {base:.0%}, lift {rate / base if base else float("nan"):.2f}, one-sided p {p:.3f}')
        result[kind] = {'alerts': s['n'], 'positive': s['pos'], 'rate': rate, 'baseline': base, 'p': p}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
