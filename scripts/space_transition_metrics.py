"""Space use and transition numbers of our team from positions.jsonl (our view: our goal left, we attack right), per half.

Used by scripts/build_kordoc_report.py. Without the ball: a "phase" is where the team centre is (opponent half = attack phase, own half = defence phase). Every number says where players stood or moved.
  hull area      convex hull of the outfield players (attack phase and defence phase; Shaw and Glickman found about 2 for the ratio attack/defence in professional matches)
  lanes final third   how many of the five lanes had a player in the final third (seconds with two or more players there)
  between lines  our players between the opponent's midfield line and defence line (only when the opponent's shape is seen)
  switches       the sideways position of the attackers in the opponent's half moved by 15 m or more within 6 s
  transitions    the team centre crossed from beyond +5 m to beyond -5 m (or back) within 25 s: how long it took and how the team looked on arrival
  shape counts   outfield players within 25 m of our goal in the defence phase, in the final third in the attack phase
"""
import math
import statistics

import build_detailed_report as R


def hull_area(points):
    pts = sorted(set((round(u, 2), round(v, 2)) for _, u, v in points))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return abs(sum(hull[i][0] * hull[(i + 1) % len(hull)][1] - hull[(i + 1) % len(hull)][0] * hull[i][1] for i in range(len(hull)))) / 2.0


def centre_series(data):
    out = {}
    for t in sorted(data):
        pts = R.outfield(data[t]['ours'])
        if len(pts) >= 7:
            out[t] = statistics.mean(p[1] for p in pts)
    return out


def smooth(series, window=3):
    out = {}
    ts = sorted(series)
    for t in ts:
        vals = [series[x] for x in range(t - window, t + window + 1) if x in series]
        out[t] = statistics.mean(vals)
    return out


def transitions(data):
    """Crossings of the team centre: ('retreat' or 'advance', start second, seconds taken, team length on arrival, defence-midfield gap on arrival)."""
    c = smooth(centre_series(data))
    ts = sorted(c)
    events = []
    state, last_high, last_low = None, None, None
    for t in ts:
        v = c[t]
        if v > 5:
            if state == 'low' and last_low is not None and t - last_low <= 25:
                events.append(('advance', last_low, t - last_low, t))
            state, last_high = 'high', t
        elif v < -5:
            if state == 'high' and last_high is not None and t - last_high <= 25:
                events.append(('retreat', last_high, t - last_high, t))
            state, last_low = 'low', t
    out = []
    for kind, start, took, arrive in events:
        sh = R.shape(data[arrive]['ours']) if arrive in data else None
        out.append({'kind': kind, 'start': start, 'seconds': took, 'length': (sh['att'] - sh['def']) if sh else None, 'gap_dm': (sh['mid'] - sh['def']) if sh else None})
    return out


def switches(data):
    ys = {}
    for t in sorted(data):
        pts = R.outfield(data[t]['ours'])
        att = [p for p in pts if p[1] > 0]
        if len(att) >= 4 and statistics.mean(p[1] for p in pts) > 0:
            ys[t] = statistics.mean(p[2] for p in att)
    ts = sorted(ys)
    events, last = [], -99
    for t in ts:
        before = [ys[x] for x in range(t - 6, t) if x in ys]
        if before and abs(ys[t] - statistics.mean(before)) >= 15 and t - last >= 10:
            events.append(t)
            last = t
    return events


def metrics(data):
    """All numbers of one half."""
    att_area, def_area, lanes_ok, lanes_n, between, between_n = [], [], 0, 0, [], 0
    inthird, inown = [], []
    for t in sorted(data):
        row = data[t]
        pts = R.outfield(row['ours'])
        if len(pts) < 8:
            continue
        centre = statistics.mean(p[1] for p in pts)
        area = hull_area(pts)
        if centre > 0:
            att_area.append(area)
            third = [p for p in pts if p[1] > R.THIRD]
            inthird.append(len(third))
            if len(third) >= 2:
                lanes = len({R.lane(p[2]) for p in third})
                lanes_n += 1
                lanes_ok += lanes >= 4
            theirs = R.shape([(i, -u, -v) for i, u, v in row['theirs']])
            if theirs:
                lo, hi = -theirs['mid'], -theirs['def']      # in our view the opponent's defence line is the larger u
                lo, hi = min(lo, hi), max(lo, hi)
                n = sum(1 for p in pts if lo < p[1] < hi)
                between.append(n)
        else:
            def_area.append(area)
            inown.append(sum(1 for p in pts if p[1] < -R.L / 2 + 25))
    tr = transitions(data)
    ret = [e for e in tr if e['kind'] == 'retreat']
    adv = [e for e in tr if e['kind'] == 'advance']
    mean = lambda xs: statistics.mean(xs) if xs else None
    return {
        'attack_seconds': len(att_area), 'defence_seconds': len(def_area),
        'hull_attack': mean(att_area), 'hull_defence': mean(def_area),
        'hull_ratio': (mean(att_area) / mean(def_area)) if att_area and def_area else None,
        'lanes4_share': (100.0 * lanes_ok / lanes_n) if lanes_n else None, 'lanes_seconds': lanes_n,
        'between_mean': mean(between), 'between_share': (100.0 * sum(1 for b in between if b >= 1) / len(between)) if between else None, 'between_seconds': len(between),
        'switches': len(switches(data)),
        'final_third_mean': mean(inthird), 'own25_mean': mean(inown),
        'retreats': len(ret), 'advances': len(adv),
        'retreat_seconds': mean([e['seconds'] for e in ret]), 'advance_seconds': mean([e['seconds'] for e in adv]),
        'retreat_gap': mean([e['gap_dm'] for e in ret if e['gap_dm'] is not None]), 'retreat_length': mean([e['length'] for e in ret if e['length'] is not None]),
        'advance_length': mean([e['length'] for e in adv if e['length'] is not None]),
    }
