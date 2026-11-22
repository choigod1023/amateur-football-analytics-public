"""Formation matchups on the SkillCorner open data (20 A-League matches, 10 Hz tracking), research only, read only.

python scripts/research_formation_matchups.py <skillcorner matches folder> [--workers 4] [--out result.json] [--perm 20000]

Per match and team:
  formation  = cut of the MEAN positions of the 10 outfield players with most samples, taken only while the team defends (opponent has the ball, sampled at 1 Hz),
               in the frame u = metres towards the goal the team attacks. The cut is app.team_formation._formation_of_depths (3 or 4 lines by depth).
               The goalkeeper is removed by his id (known from match.json), not by the depth rule.
  role check = the starting line-up of match.json (position acronyms) gives the number of defenders and forwards; compared with the tracking formation as a cross-check.
  shots      = player_possession events whose end_type is 'shot'; box shots = the same with penalty_area_end True. Goals = final score (own goals are included, 20 matches).
  shape      = while the team defends: height of the 4 deepest outfield players above their own goal line, the gap between those 4 and the next 4 (space between lines),
               and the width (max v - min v of outfield players).
Statistics: per formation pair, matches are oriented so that the first formation is X; the difference X minus Y is tested with an exact (n <= 15) or random
sign-flip permutation test, a 95 % interval (t for the mean of n matches), then Holm and Benjamini-Hochberg over all tested pairs.
A pair seen in fewer than 3 matches is listed but not tested. The mirror (same formation on both sides) has no meaningful orientation (the sign of the difference is arbitrary) and is not tested.
The mean-position cut keeps the back line at 3 to 5 players and every line at 5 or fewer (the unconstrained cut produced shapes such as 2-3-3-2).
Limits: 20 matches only, positions of players outside the broadcast view are extrapolated, the formation is where players stood, not a plan, professional A-League only.
"""
import argparse
import csv
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.team_formation import _formation_of_depths, _split_error, FOUR_LINES_GAIN  # noqa: E402

FPS = 10
SAMPLE = 10            # frames between samples for means and shape (1 Hz)
SNAP = 100             # frames between samples for the snapshot formation (0.1 Hz)
HALF_LENGTH = 52.5

T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
        15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 25: 2.060, 30: 2.042, 39: 2.023}


def t_crit(df):
    if df < 1:
        return float('nan')
    keys = sorted(T975)
    for k in keys:
        if df <= k:
            return T975[k]
    return 1.96


def mean_ci(values):
    """-> (n, mean, low, high); the interval is the t interval of the mean (needs n >= 2)."""
    v = np.asarray(values, float)
    n = len(v)
    if n == 0:
        return 0, float('nan'), float('nan'), float('nan')
    m = float(v.mean())
    if n < 2:
        return n, m, float('nan'), float('nan')
    half = t_crit(n - 1) * float(v.std(ddof=1)) / math.sqrt(n)
    return n, m, m - half, m + half


def constrained_formation(depths):
    """Same cut as app.team_formation (3 or 4 lines by depth, four lines only when clearly better) but the back line must have 3 to 5 players and no line more than 5.
    The unconstrained cut of MEAN positions gave shapes such as 2-3-3-2 that no team plays, because the mean depth of a whole half blurs the lines."""
    n = len(depths)
    best = {}
    for lines in (3, 4):
        found = None
        for cuts in itertools.combinations(range(1, n), lines - 1):
            bounds = [0, *cuts, n]
            sizes = [b - a for a, b in zip(bounds, bounds[1:])]
            if not 3 <= sizes[0] <= 5 or max(sizes) > 5:
                continue
            err = _split_error(depths, cuts)
            if found is None or err < found[0]:
                found = (err, sizes)
        best[lines] = found
    three, four = best[3], best[4]
    if four and three and three[0] > 0 and four[0] <= FOUR_LINES_GAIN * three[0]:
        chosen = four
    else:
        chosen = three or four
    return '-'.join(map(str, chosen[1])) if chosen else None


def role_counts(info, team):
    roles = [p['player_role']['acronym'] for p in info['players'] if p['team_id'] == team and p['start_time'] == '00:00:00']
    back = sum(r in ('CB', 'LCB', 'RCB', 'MCB', 'LB', 'RB') for r in roles)
    wing_backs = sum(r in ('LWB', 'RWB') for r in roles)
    centre_backs = sum(r in ('CB', 'LCB', 'RCB', 'MCB') for r in roles)
    # with three centre backs the wing backs make a five-man line, otherwise they are full backs
    defenders = back + wing_backs
    forwards = sum(r in ('CF', 'LF', 'RF') for r in roles)
    return {'roles': sorted(roles), 'defenders': defenders, 'forwards': forwards, 'centre_backs': centre_backs}


def process_match(folder):
    folder = Path(folder)
    mid = folder.name
    info = json.loads((folder / f'{mid}_match.json').read_text(encoding='utf-8'))
    home, away = info['home_team']['id'], info['away_team']['id']
    teams = (home, away)
    team_of = {p['id']: p['team_id'] for p in info['players']}
    gk = {p['id'] for p in info['players'] if p['player_role']['acronym'] == 'GK'}
    shots = {t: 0 for t in teams}
    box = {t: 0 for t in teams}
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
                shots[team] += 1
                box[team] += r['penalty_area_end'] == 'True'
    group_name = {home: 'home team', away: 'away team'}
    acc = {t: defaultdict(lambda: [0.0, 0.0, 0]) for t in teams}      # player -> [sum u, sum v, n] while defending
    shape = {t: {'height': [], 'gap': [], 'width': []} for t in teams}
    snaps = {t: [] for t in teams}
    with open(folder / f'{mid}_tracking_extrapolated.jsonl', encoding='utf-8') as f:
        for line in f:
            if '"period": null' in line[:80]:
                continue
            d = json.loads(line)
            frame, period = d['frame'], d['period']
            if period is None or frame % SAMPLE:
                continue
            group = d['possession']['group']
            if group not in ('home team', 'away team'):
                continue
            for t in teams:
                if group == group_name[t] or (t, period) not in direction:
                    continue                      # only while this team defends
                sign = direction[(t, period)]
                pts = []
                for p in d['player_data']:
                    pid = p['player_id']
                    if p['x'] is None or team_of.get(pid) != t or pid in gk:
                        continue
                    pts.append((pid, p['x'] * sign, p['y'] * sign))
                for pid, u, v in pts:
                    a = acc[t][pid]
                    a[0] += u; a[1] += v; a[2] += 1
                if len(pts) >= 9:
                    us = sorted(u for _, u, _ in pts)
                    vs = [v for _, _, v in pts]
                    k = min(4, len(us) // 2)
                    shape[t]['height'].append(float(np.mean(us[:k])) + HALF_LENGTH)
                    shape[t]['gap'].append(float(np.mean(us[k:2 * k])) - float(np.mean(us[:k])))
                    shape[t]['width'].append(max(vs) - min(vs))
                if len(pts) == 10 and frame % SNAP == 0:
                    snaps[t].append(_formation_of_depths(sorted(u for _, u, _ in pts), True)['text'])
    out = {'match': mid, 'teams': {}}
    for t in teams:
        top = sorted(acc[t].items(), key=lambda kv: -kv[1][2])[:10]
        mean_u = sorted(a[0] / a[2] for _, a in top)
        text = constrained_formation(mean_u) if len(mean_u) == 10 else None
        mode = Counter(snaps[t]).most_common(1)
        score = info['home_team_score'] if t == home else info['away_team_score']
        conceded = info['away_team_score'] if t == home else info['home_team_score']
        out['teams'][str(t)] = {
            'team': t, 'opponent': away if t == home else home, 'formation': text, 'samples_defending': int(top[0][1][2]) if top else 0,
            'snapshot_mode': mode[0][0] if mode else None, 'snapshot_mode_share': round(mode[0][1] / len(snaps[t]), 3) if mode else None, 'snapshots': len(snaps[t]),
            'shots': shots[t], 'box_shots': box[t], 'goals': score, 'conceded': conceded,
            'height': float(np.mean(shape[t]['height'])) if shape[t]['height'] else None,
            'gap': float(np.mean(shape[t]['gap'])) if shape[t]['gap'] else None,
            'width': float(np.mean(shape[t]['width'])) if shape[t]['width'] else None,
            'shape_samples': len(shape[t]['height']), **role_counts(info, t)}
    return out


def sign_flip_p(diffs, rng, perm):
    d = np.asarray(diffs, float)
    n = len(d)
    obs = abs(d.mean())
    if n <= 15:
        signs = np.array(list(itertools.product((1, -1), repeat=n)))
        stats = np.abs((signs * d).mean(axis=1))
    else:
        signs = rng.choice((1, -1), size=(perm, n))
        stats = np.abs((signs * d).mean(axis=1))
    return float((stats >= obs - 1e-12).mean())


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out = [None] * len(ps)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        out[i] = running
    return out


def bh(ps):
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i], reverse=True)
    out = [None] * m
    running = 1.0
    for rank, i in enumerate(order):
        running = min(running, ps[i] * m / (m - rank))
        out[i] = running
    return out


def rank(a):
    a = np.asarray(a, float)
    order = a.argsort(kind='mergesort')
    r = np.empty(len(a))
    r[order] = np.arange(len(a))
    for v in np.unique(a):                     # average ranks for ties
        idx = a == v
        if idx.sum() > 1:
            r[idx] = r[idx].mean()
    return r


def spearman(x, y):
    x, y = rank(x), rank(y)
    if x.std() == 0 or y.std() == 0:
        return float('nan')
    return float(np.corrcoef(x, y)[0, 1])


def cluster_bootstrap_spearman(x, y, cluster, rng, reps=4000):
    """95 % interval of Spearman rho when the two rows of a match are resampled together."""
    x, y, cluster = np.asarray(x, float), np.asarray(y, float), np.asarray(cluster)
    ids = sorted(set(cluster.tolist()))
    index = {c: np.where(cluster == c)[0] for c in ids}
    vals = []
    for _ in range(reps):
        pick = rng.choice(len(ids), size=len(ids))
        rows = np.concatenate([index[ids[i]] for i in pick])
        r = spearman(x[rows], y[rows])
        if not math.isnan(r):
            vals.append(r)
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def eta_squared(groups, values):
    values = np.asarray(values, float)
    labels = np.asarray(groups)
    total = ((values - values.mean()) ** 2).sum()
    if total == 0:
        return 0.0
    between = sum(((values[labels == g] - values.mean()) ** 2).sum() * 0 + (labels == g).sum() * (values[labels == g].mean() - values.mean()) ** 2 for g in set(labels))
    return float(between / total)


def eta_with_perm(groups, values, rng, perm=5000):
    obs = eta_squared(groups, values)
    labels = np.asarray(groups)
    null = [eta_squared(rng.permutation(labels), values) for _ in range(perm)]
    return obs, float(np.mean(null)), float((np.array(null) >= obs - 1e-12).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('matches')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--out', default=None)
    ap.add_argument('--perm', type=int, default=20000)
    a = ap.parse_args()
    folders = sorted(p for p in Path(a.matches).iterdir() if p.is_dir())
    with ProcessPoolExecutor(min(a.workers, 4)) as ex:
        results = list(ex.map(process_match, folders))
    rng = np.random.default_rng(20261117)
    rows = []
    for r in results:
        for t, v in r['teams'].items():
            opp = r['teams'][str(v['opponent'])]
            rows.append({**v, 'match': r['match'], 'opp_formation': opp['formation'], 'opp_height': opp['height'], 'opp_gap': opp['gap'],
                         'opp_width': opp['width'], 'opp_shots': opp['shots'], 'opp_box': opp['box_shots']})
    report = {'matches': len(results), 'team_matches': len(rows), 'rows': rows}

    # 1. formations and checks
    counts = Counter(r['formation'] for r in rows)
    report['formation_counts'] = dict(counts.most_common())
    share = [r['snapshot_mode_share'] for r in rows if r['snapshot_mode_share'] is not None]
    report['snapshot_mode_share'] = {'n': len(share), 'mean': float(np.mean(share)), 'min': float(np.min(share)), 'max': float(np.max(share))}
    fam = lambda s: int(s.split('-')[0]) if s else None
    agree_def = [fam(r['formation']) == r['defenders'] for r in rows if r['formation']]
    report['role_check'] = {'defenders_agree': [int(sum(agree_def)), len(agree_def)]}
    last = lambda s: int(s.split('-')[-1]) if s else None
    agree_fw = [last(r['formation']) == r['forwards'] for r in rows if r['formation']]
    report['role_check']['forwards_agree'] = [int(sum(agree_fw)), len(agree_fw)]

    # 2. pairs, one entry per match, oriented X vs Y with X <= Y by name
    def pair_table(key_of):
        pair_rows = defaultdict(list)
        for r in results:
            a_id, b_id = list(r['teams'])
            A, B = r['teams'][a_id], r['teams'][b_id]
            if not A['formation'] or not B['formation']:
                continue
            ka, kb = key_of(A['formation']), key_of(B['formation'])
            x, y = (A, B) if ka <= kb else (B, A)
            pair_rows[tuple(sorted((ka, kb)))].append(
                {'match': r['match'], 'shots': x['shots'] - y['shots'], 'box': x['box_shots'] - y['box_shots'], 'goals': x['goals'] - y['goals']})
        pairs = []
        for (fx, fy), items in sorted(pair_rows.items(), key=lambda kv: -len(kv[1])):
            entry = {'x': fx, 'y': fy, 'n': len(items), 'mirror': fx == fy}
            for key in ('shots', 'box', 'goals'):
                entry[key] = dict(zip(('n', 'mean', 'low', 'high'), mean_ci([i[key] for i in items])))
                ok = len(items) >= 3 and not entry['mirror']
                entry['p_' + key] = sign_flip_p([i[key] for i in items], rng, a.perm) if ok else None
            pairs.append(entry)
        tested = [p for p in pairs if p['p_shots'] is not None]
        for key in ('shots', 'box', 'goals'):
            ps = [p['p_' + key] for p in tested]
            if ps:
                for p, h, bb in zip(tested, holm(ps), bh(ps)):
                    p['holm_' + key] = h
                    p['bh_' + key] = bb
        return pairs, tested

    pairs, tested = pair_table(lambda f: f)
    report['pairs'] = pairs
    report['tested_pairs'] = len(tested)
    report['mirror_matches'] = int(sum(p['n'] for p in pairs if p['mirror']))
    fam_pairs, fam_tested = pair_table(lambda f: f.split('-')[0] + ' back')
    report['family_pairs'] = fam_pairs
    report['family_tested_pairs'] = len(fam_tested)

    # 3. by own formation, and opponent formation (team level, rows of one match are dependent)
    by_own = defaultdict(list)
    for r in rows:
        if r['formation']:
            by_own[r['formation']].append(r)
    report['by_own_formation'] = {f: {k: dict(zip(('n', 'mean', 'low', 'high'), mean_ci([x[k] for x in v]))) for k in ('shots', 'box_shots', 'goals')} for f, v in by_own.items()}
    valid = [r for r in rows if r['formation'] and r['opp_formation']]
    y_shots = [r['shots'] for r in valid]
    report['eta_own_formation_vs_shots'] = dict(zip(('eta2', 'null_mean', 'perm_p'), eta_with_perm([r['formation'] for r in valid], y_shots, rng)))
    report['eta_opp_formation_vs_shots'] = dict(zip(('eta2', 'null_mean', 'perm_p'), eta_with_perm([r['opp_formation'] for r in valid], y_shots, rng)))
    # the largest absolute pair difference in shots (pairs seen in >= 3 matches) compared with random relabelling of formations
    obs_max = max((abs(p['shots']['mean']) for p in tested), default=0.)
    labels = [(r['match'], r['teams']) for r in results]
    exceed = 0
    reps = 1000
    pool = [t['formation'] for r in results for t in r['teams'].values() if t['formation']]
    for _ in range(reps):
        perm_pool = rng.permutation(pool)
        k = 0
        tmp = defaultdict(list)
        for r in results:
            ts = list(r['teams'].values())
            if not all(t['formation'] for t in ts):
                continue
            fa, fb = perm_pool[k], perm_pool[k + 1]
            k += 2
            if fa == fb:
                continue
            (x, y) = (ts[0], ts[1]) if fa <= fb else (ts[1], ts[0])
            fx, fy = (fa, fb) if fa <= fb else (fb, fa)
            tmp[(fx, fy)].append(x['shots'] - y['shots'])
        big = [abs(np.mean(v)) for v in tmp.values() if len(v) >= 3]
        if big and max(big) >= obs_max:
            exceed += 1
    report['max_pair_shot_diff'] = {'observed': obs_max, 'random_relabel_p': exceed / reps, 'reps': reps}

    # 4. shape values against shots, opponent shape while it defends
    corr = {}
    for key in ('height', 'width', 'gap'):
        for label, field, target in (('opponent_shape_vs_our_shots', 'opp_' + key, 'shots'), ('opponent_shape_vs_our_box_shots', 'opp_' + key, 'box_shots'),
                                     ('own_shape_vs_opponent_shots', key, 'opp_shots')):
            rr = [r for r in rows if r[field] is not None]
            x = [r[field] for r in rr]
            y = [r[target] for r in rr]
            lo, hi = cluster_bootstrap_spearman(x, y, [r['match'] for r in rr], rng)
            corr[f'{label}:{key}'] = {'n': len(rr), 'rho': spearman(x, y), 'low': lo, 'high': hi}
    report['shape_correlations'] = corr
    report['shape_means'] = {k: dict(zip(('n', 'mean', 'low', 'high'), mean_ci([r[k] for r in rows if r[k] is not None]))) for k in ('height', 'gap', 'width')}
    if a.out:
        Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, ensure_ascii=False, indent=1, default=float))


if __name__ == '__main__':
    main()
