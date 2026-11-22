"""Set pieces: how many attackers / defenders were in the box and did the restart lead to a shot? (research, read only, SkillCorner open data)

python scripts/research_set_pieces.py <skillcorner data folder> [--out result.json]

A set piece = a player_possession event in <match>_dynamic_events.csv whose game_interruption_before is corner_for, free_kick_for or throw_in_for
(= the first possession after that restart; the kick itself is not an event, so the frame is the moment the first player receives the ball, estimate of the restart moment).
At that frame the 10 fps tracking (<match>_tracking_extrapolated.jsonl) gives player positions, turned so that the attacking team always attacks to +x.
Features: attackers in the penalty area (the kick taker and the goalkeepers are counted as ordinary players, see GK note below), defenders in the penalty area (goalkeeper not counted),
attackers and defenders within 30 m of the goal centre, and box balance = attackers - defenders.
Outcome: the possession phase of that event (phases_of_play.csv, same phase_index) led to a shot / goal. Second outcome: a shot by the same team within 15 s (end_type == shot).
Tables: shot rate per feature bin with 95 % Wilson interval, pooled AUC of the feature for shot with a match-wise permutation p, and the per-match direction (AUC > 0.5).
Reading: this is a description of 20 professional matches. It is a correlation, not a cause: a corner into a crowded box is also a corner the team chose to take short or long,
tracking is partly extrapolated (is_detected false), and a shot can come from the next phase. Cells below 30 set pieces are marked.
"""
import argparse
import collections
import csv
import json
import random
from math import sqrt
from pathlib import Path

import numpy as np

KINDS = {'corner_for': 'corner', 'free_kick_for': 'free_kick', 'throw_in_for': 'throw_in'}
BOX_DEPTH = 16.5
BOX_HALF_WIDTH = 20.16
ZONE_RADIUS = 30.0
ATTACKING_THIRD_FRACTION = 1 / 6  # attacking third starts at x >= length/2 - length/3 = length/6 from the centre


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - a) / d, (c + a) / d


def auc(values, labels):
    """Mann-Whitney AUC of values for label 1 (ties count half). None if one class is missing."""
    v = np.asarray(values, dtype=float)
    y = np.asarray(labels, dtype=bool)
    pos, neg = v[y], v[~y]
    if len(pos) == 0 or len(neg) == 0:
        return None
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    return float((gt + 0.5 * eq) / (len(pos) * len(neg)))


def load_match(folder):
    mid = folder.name
    match = json.loads((folder / f'{mid}_match.json').read_text(encoding='utf-8'))
    length, width = float(match['pitch_length']), float(match['pitch_width'])
    team_of, role_of = {}, {}
    for p in match['players']:
        team_of[p['id']] = p['team_id']
        role_of[p['id']] = p['player_role']['acronym']
    with open(folder / f'{mid}_dynamic_events.csv', encoding='utf-8') as f:
        events = [r for r in csv.DictReader(f)]
    with open(folder / f'{mid}_phases_of_play.csv', encoding='utf-8') as f:
        phases = {r['index']: r for r in csv.DictReader(f)}
    poss = [r for r in events if r['event_type'] == 'player_possession']
    restarts = [r for r in poss if r['game_interruption_before'] in KINDS]
    need = {int(r['frame_start']) for r in restarts}
    frames = {}
    with open(folder / f'{mid}_tracking_extrapolated.jsonl', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i in need:
                d = json.loads(line)
                frames[d['frame']] = d
    rows = []
    for r in restarts:
        fr = int(r['frame_start'])
        d = frames.get(fr)
        if d is None or not d['player_data'] or d['ball_data']['x'] is None:
            continue
        sign = 1.0 if r['attacking_side'] == 'left_to_right' else -1.0
        team = int(r['team_id'])
        att, dfn, n_det, n_all = [], [], 0, 0
        for p in d['player_data']:
            pid = p['player_id']
            if pid not in team_of or p['x'] is None:
                continue
            x, y = sign * p['x'], sign * p['y']
            n_all += 1
            n_det += bool(p['is_detected'])
            (att if team_of[pid] == team else dfn).append((x, y, role_of[pid]))
        if len(att) < 8 or len(dfn) < 8:
            continue
        goal_x = length / 2

        def in_box(q):
            return q[0] >= goal_x - BOX_DEPTH and abs(q[1]) <= BOX_HALF_WIDTH

        def in_zone(q):
            return ((q[0] - goal_x) ** 2 + q[1] ** 2) ** 0.5 <= ZONE_RADIUS

        bx = sign * d['ball_data']['x']
        by = sign * d['ball_data']['y']
        att_box = sum(in_box(q) for q in att)
        def_box = sum(in_box(q) for q in dfn if q[2] != 'GK')
        phase = phases.get(r['phase_index'])
        shot_phase = bool(phase) and phase['team_possession_lead_to_shot'] == 'True'
        goal_phase = bool(phase) and phase['team_possession_lead_to_goal'] == 'True'
        shot_15s = any(e['team_id'] == r['team_id'] and e['end_type'] == 'shot' and fr <= int(e['frame_start']) <= fr + 150 for e in poss)
        rows.append({
            'match': mid, 'frame': fr, 'period': int(r['period']), 'kind': KINDS[r['game_interruption_before']],
            'ball_x': bx, 'ball_y': by, 'att_third': bx >= length * ATTACKING_THIRD_FRACTION,
            'att_box': att_box, 'def_box': def_box, 'balance': att_box - def_box,
            'att_zone': sum(in_zone(q) for q in att), 'def_zone': sum(in_zone(q) for q in dfn if q[2] != 'GK'),
            'detected_share': n_det / n_all if n_all else 0.0,
            'shot': shot_phase, 'goal': goal_phase, 'shot_15s': shot_15s,
            'phase_type': phase['team_in_possession_phase_type'] if phase else '',
        })
    return rows


def bins_for(feature):
    if feature in ('att_box', 'att_zone'):
        return [('0', lambda v: v == 0), ('1-2', lambda v: 1 <= v <= 2), ('3-4', lambda v: 3 <= v <= 4), ('5+', lambda v: v >= 5)]
    if feature in ('def_box', 'def_zone'):
        return [('0-3', lambda v: v <= 3), ('4-6', lambda v: 4 <= v <= 6), ('7+', lambda v: v >= 7)]
    return [('<=-3', lambda v: v <= -3), ('-2..0', lambda v: -2 <= v <= 0), ('+1..+2', lambda v: 1 <= v <= 2), ('>=+3', lambda v: v >= 3)]


def permutation_p(rows, feature, outcome, reps=2000, seed=1):
    """Two sided p for the pooled AUC; outcome labels are shuffled inside each match, so match differences do not create the effect."""
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[r['match']].append(i)
    vals = np.array([r[feature] for r in rows], dtype=float)
    lab = np.array([r[outcome] for r in rows], dtype=bool)
    obs = auc(vals, lab)
    if obs is None:
        return None
    hits = 0
    for _ in range(reps):
        sh = lab.copy()
        for idx in by.values():
            sub = [lab[i] for i in idx]
            rng.shuffle(sub)
            for i, s in zip(idx, sub):
                sh[i] = s
        a = auc(vals, sh)
        if abs(a - 0.5) >= abs(obs - 0.5):
            hits += 1
    return (hits + 1) / (reps + 1)


def analyse(rows, name, features, outcome='shot'):
    n = len(rows)
    k = sum(r[outcome] for r in rows)
    lo, hi = wilson(k, n)
    print(f'\n== {name}: {n} set pieces from {len(set(r["match"] for r in rows))} matches, {outcome} {k} ({k / n:.1%}, 95% {lo:.1%}-{hi:.1%}), goals {sum(r["goal"] for r in rows)}' if n else f'\n== {name}: 0')
    out = {'n': n, 'matches': len(set(r['match'] for r in rows)), 'outcome': outcome, 'events_with_outcome': k, 'rate': k / n if n else None,
           'wilson95': [lo, hi], 'goals': sum(r['goal'] for r in rows), 'features': {}}
    if n < 30:
        print('  fewer than 30 set pieces: tables below are only for reference')
    for feat in features:
        entry = {'bins': []}
        print(f'  feature {feat}')
        for label, fn in bins_for(feat):
            g = [r for r in rows if fn(r[feat])]
            if not g:
                continue
            gk = sum(r[outcome] for r in g)
            glo, ghi = wilson(gk, len(g))
            per = collections.defaultdict(lambda: [0, 0])
            for r in g:
                per[r['match']][0] += 1
                per[r['match']][1] += r[outcome]
            entry['bins'].append({'bin': label, 'n': len(g), 'events': gk, 'rate': gk / len(g), 'lo': glo, 'hi': ghi, 'goals': sum(r['goal'] for r in g), 'matches': len(per)})
            print(f'    {label:7s} n {len(g):4d} {outcome} {gk:3d} ({gk / len(g):5.1%}, 95% {glo:.1%}-{ghi:.1%}) matches {len(per):2d}{"  <30" if len(g) < 30 else ""}')
        a = auc([r[feat] for r in rows], [r[outcome] for r in rows])
        per_auc, up, down = [], 0, 0
        for mid in sorted(set(r['match'] for r in rows)):
            sub = [r for r in rows if r['match'] == mid]
            pa = auc([r[feat] for r in sub], [r[outcome] for r in sub])
            if pa is None:
                continue
            per_auc.append(pa)
            up += pa > 0.5
            down += pa < 0.5
        p = permutation_p(rows, feat, outcome) if a is not None else None
        entry.update({'pooled_auc': a, 'perm_p': p, 'matches_with_both_classes': len(per_auc), 'matches_auc_above_half': up, 'matches_auc_below_half': down})
        if a is not None:
            print(f'    pooled AUC {a:.3f} (0.5 = no relation), match-wise permutation p {p:.3f}; matches with a shot and a non-shot: {len(per_auc)}, AUC above 0.5 in {up}, below in {down}')
        out['features'][feat] = entry
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder')
    parser.add_argument('--out')
    args = parser.parse_args()
    root = Path(args.folder) / 'data' / 'matches'
    rows = []
    skipped = collections.Counter()
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        got = load_match(folder)
        rows.extend(got)
        print(f'{folder.name}: {len(got)} set pieces ({collections.Counter(r["kind"] for r in got)})')
    print(f'\ntotal {len(rows)} set pieces, mean share of detected (not extrapolated) players at that frame {np.mean([r["detected_share"] for r in rows]):.1%}')
    feats = ['att_box', 'def_box', 'balance', 'att_zone']
    result = {'definition': __doc__, 'by_kind': {}, 'detected_share_mean': float(np.mean([r['detected_share'] for r in rows]))}
    for kind in ('corner', 'free_kick', 'throw_in'):
        sub = [r for r in rows if r['kind'] == kind]
        result['by_kind'][kind + '_all'] = analyse(sub, kind + ' (all places)', [] if kind != 'corner' else feats)
        if kind != 'corner':
            third = [r for r in sub if r['att_third']]
            result['by_kind'][kind + '_attacking_third'] = analyse(third, kind + ' (ball in attacking third)', feats)
    crowd = [r for r in rows if r['kind'] == 'corner' or (r['att_third'] and r['kind'] != 'throw_in')]
    result['by_kind']['corner_and_attacking_free_kick'] = analyse(crowd, 'corner + free kick in attacking third', feats)
    result['by_kind']['corner_goal_or_shot_15s'] = analyse([r for r in rows if r['kind'] == 'corner'], 'corner, outcome = shot within 15 s', ['att_box', 'def_box'], outcome='shot_15s')
    all_rows = {'rows': len(rows), 'shot_rate_all': sum(r['shot'] for r in rows) / len(rows)}
    print(f'\nall set pieces: shot rate {all_rows["shot_rate_all"]:.1%}')
    result['overall'] = all_rows
    print('\nThis is correlation in 20 professional matches, not cause and effect.')
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1, default=float), encoding='utf-8')


if __name__ == '__main__':
    main()
