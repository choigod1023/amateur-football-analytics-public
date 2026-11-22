"""Research only: join broken team B track pieces across LONG gaps (seconds to tens of seconds) with metre positions, team and depth-line constraints.

python scripts/research_gap_link.py <review store> <tracks.json> <camera> <direction> <bg a,b,tx,ty> <schedule> <half name h1|h2> [--max-gap 40] [--out result.json]

The stored tracks (app/track_stitch.py already joined gaps of at most 1.6 s in pixel space) still hold about 200 team B pieces per half for 11 players.
This script only reads: it changes no track file and no label. For every pair "piece a ends, piece b starts later" it scores
  * the distance between the two team-relative positions (a's last 1 s and b's first 1 s, both measured from the centre of team B of that moment, so that the
    movement of the whole team cancels out), divided by an allowed distance that grows with the gap,
  * a speed limit on the absolute metre positions,
  * the depth-line (defence, midfield, attack) of both pieces,
  * no overlap in time and the same team.
Methods: V1 position only (Hungarian), V2 position + line (Hungarian), V3 position + line, greedy, and a limit of 11 chains alive at the same time.
Checks: (a) the human answers (links same/different, assign; answers read by the computer from photos are kept apart), (b) a synthetic test: a long piece is cut
into two with a gap and we see whether the method joins the two halves again. Both checks are small, see the printed counts.
"""
import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.pitch_map import fit  # noqa: E402
from build_tactical_report import metre_rows  # noqa: E402
from build_team_minimap import parse_schedule  # noqa: E402

FPS = 5.0
EDGE = 5                      # frames (1 s) used at the start and end of a piece
NOISE = 3.0                   # metres of position noise
GROWTH = 2.5                  # metres of allowed extra offset per sqrt(second) of gap
MAX_RATIO = 2.0               # a pair is possible when distance <= MAX_RATIO * allowed
SPEED = 7.0                   # m/s, absolute speed limit (plus 4 m of noise)
LINE_LIMIT = 0.35             # allowed difference of the depth-line value (0 = deepest, 1 = most advanced)
CAPACITY = 11                 # chains alive (first start to last end) at one moment
LINE_WEIGHT = 2.0


def load_pieces(tracks_path, fitted, direction, bg, schedule, min_rows=10):
    """-> list of pieces of team B: {'id', 'frames' (array), 'uv' (n x 2 oriented metres), 'rel' (n x 2 relative to the team centre), 'line' (n)} and the team centre by frame."""
    result = json.loads(Path(tracks_path).read_text(encoding='utf-8'))
    b_tracks = {t: rows for t, rows in result['tracks'].items() if sum(r['team'] == 'B' for r in rows) > len(rows) / 2}
    by_frame, _ = metre_rows({t: [r for r in rows if r['team'] == 'B'] for t, rows in b_tracks.items()}, fitted, schedule, bg, 0, result['frames'])
    per_track = defaultdict(list)
    centre, rank = {}, {}
    for frame, teams in by_frame.items():
        players = teams.get('B', [])
        if len(players) < 4:
            continue
        us = np.array([x * direction for _, x, _ in players])
        vs = np.array([y * direction for _, _, y in players])
        centre[frame] = (us.mean(), vs.mean())
        order = us.argsort().argsort() / (len(players) - 1)
        for (tid, _, _), u, v, o in zip(players, us, vs, order):
            per_track[tid].append((frame, u, v, u - us.mean(), v - vs.mean(), o))
    pieces = []
    for tid, rows in per_track.items():
        rows.sort()
        if len(rows) < min_rows:
            continue
        a = np.array(rows)
        pieces.append({'id': tid, 'frames': a[:, 0].astype(int), 'uv': a[:, 1:3], 'rel': a[:, 3:5], 'line': a[:, 5]})
    pieces.sort(key=lambda p: p['frames'][0])
    return pieces, len(b_tracks), result['frames']


def summarise(p):
    p['start'], p['end'] = int(p['frames'][0]), int(p['frames'][-1])
    k = min(EDGE, len(p['frames']))
    p['rel_start'], p['rel_end'] = p['rel'][:k].mean(axis=0), p['rel'][-k:].mean(axis=0)
    p['uv_start'], p['uv_end'] = p['uv'][:k].mean(axis=0), p['uv'][-k:].mean(axis=0)
    p['line_mean'] = float(np.median(p['line']))


def pair_cost(a, b, max_gap, use_line):
    gap = (b['start'] - a['end']) / FPS
    if gap <= 0 or gap > max_gap:
        return None
    allowed = NOISE + GROWTH * math.sqrt(gap)
    d_rel = float(np.hypot(*(b['rel_start'] - a['rel_end'])))
    if d_rel > MAX_RATIO * allowed:
        return None
    if float(np.hypot(*(b['uv_start'] - a['uv_end']))) > SPEED * gap + 4.0:
        return None
    line = abs(a['line_mean'] - b['line_mean'])
    if use_line and line > LINE_LIMIT:
        return None
    return d_rel / allowed + (LINE_WEIGHT * line if use_line else 0.0)


def cost_matrix(pieces, max_gap, use_line):
    n = len(pieces)
    big = 1e6
    m = np.full((n, n), big)
    for i, a in enumerate(pieces):
        for j, b in enumerate(pieces):
            if i != j and b['start'] > a['end']:
                c = pair_cost(a, b, max_gap, use_line)
                if c is not None:
                    m[i, j] = c
    return m, big


def hungarian_links(pieces, max_gap, use_line):
    m, big = cost_matrix(pieces, max_gap, use_line)
    try:
        from scipy.optimize import linear_sum_assignment
        rows, cols = linear_sum_assignment(m)
    except ImportError:                                  # the project environment has lap but not scipy
        import lap
        _cost, x, _y = lap.lapjv(m, extend_cost=True)
        rows, cols = np.arange(len(x)), x
    return [(int(i), int(j)) for i, j in zip(rows, cols) if j >= 0 and m[i, j] < big]


def greedy_links(pieces, max_gap, use_line, capacity=None, total=None):
    m, big = cost_matrix(pieces, max_gap, use_line)
    n = len(pieces)
    order = sorted(((m[i, j], i, j) for i in range(n) for j in range(n) if m[i, j] < big))
    nxt, prev = {}, {}
    chain_of = list(range(n))                        # chain id of each piece
    spans = {i: [pieces[i]['start'], pieces[i]['end']] for i in range(n)}
    count = None
    if capacity:
        count = np.zeros(total + 2, dtype=int)
        for p in pieces:
            count[p['start']:p['end'] + 1] += 1
    links = []
    for _c, i, j in order:
        if i in nxt or j in prev or chain_of[i] == chain_of[j]:
            continue
        ci, cj = chain_of[i], chain_of[j]
        if spans[ci][1] >= spans[cj][0]:             # the two chains overlap in time: one person cannot be both
            continue
        if capacity:
            lo, hi = spans[ci][1] + 1, spans[cj][0]
            if hi > lo and count[lo:hi].max() + 1 > capacity:
                continue
            count[lo:hi] += 1
        nxt[i], prev[j] = j, i
        links.append((i, j))
        new = [spans[ci][0], spans[cj][1]]
        for k in range(n):
            if chain_of[k] == cj:
                chain_of[k] = ci
        spans[ci] = new
        del spans[cj]
    return links


def chains_from(links, n):
    nxt = dict(links)
    has_prev = {j for _, j in links}
    chains = []
    for i in range(n):
        if i not in has_prev:
            chain, k = [i], i
            while k in nxt:
                k = nxt[k]
                chain.append(k)
            chains.append(chain)
    return chains


def span_count(chains, pieces, total):
    count = np.zeros(total + 2, dtype=int)
    for chain in chains:
        count[pieces[chain[0]]['start']:pieces[chain[-1]]['end'] + 1] += 1
    return count


def alive_count(pieces, total):
    count = np.zeros(total + 2, dtype=int)
    for p in pieces:
        count[p['start']:p['end'] + 1] += 1
    return count


def human_truth(store, half):
    """-> (player of each track by human answer, player by computer-read number, same pairs, different pairs)."""
    players = Path(store) / 'players'
    assign = json.loads((players / 'assign' / f'{half}.json').read_text(encoding='utf-8'))
    links = json.loads((players / 'links' / f'{half}.json').read_text(encoding='utf-8'))
    notes = json.loads((players / 'auto_notes.json').read_text(encoding='utf-8')).get('notes', {}).get(half, {})
    auto = {t for t in assign if t in notes}
    human = {t: p for t, p in assign.items() if t not in auto}
    return human, {t: assign[t] for t in auto}, [tuple(p) for p in links['same']], [tuple(p) for p in links['different']]


def person_clusters(assign_all, same_pairs):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in same_pairs:
        parent[find(a)] = find(b)
    by_player = {}
    for t, p in assign_all.items():
        if p in by_player:
            parent[find(t)] = find(by_player[p])
        else:
            by_player[p] = t
        find(t)
    return find


def evaluate_human(chains, pieces, human, auto, same_pairs, diff_pairs, with_auto):
    ids = [p['id'] for p in pieces]
    assign = {**auto, **human} if with_auto else dict(human)
    find = person_clusters(assign, same_pairs)
    diff = {frozenset(p) for p in diff_pairs}
    labelled_links = confirmed = conflicts = 0
    conflicting_chains = 0
    for chain in chains:
        members = [ids[k] for k in chain]
        players = {assign[m] for m in members if m in assign}
        if len(players) > 1 or any(frozenset((a, b)) in diff for a in members for b in members if a != b):
            conflicting_chains += 1
        for x, y in zip(members, members[1:]):
            known_x = x in assign or any(x in pair for pair in same_pairs)
            known_y = y in assign or any(y in pair for pair in same_pairs)
            if frozenset((x, y)) in diff or (x in assign and y in assign and assign[x] != assign[y]):
                labelled_links += 1
                conflicts += 1
            elif known_x and known_y and find(x) == find(y):
                labelled_links += 1
                confirmed += 1
    # recall: consecutive pieces in time of the same person that the method put in one chain
    chain_of = {ids[k]: ci for ci, chain in enumerate(chains) for k in chain}
    start = {p['id']: p['start'] for p in pieces}
    groups = defaultdict(list)
    tracks_known = set(assign) | {t for pair in same_pairs for t in pair}
    for t in tracks_known:
        if t in start:
            groups[find(t)].append(t)
    pairs = joined = 0
    end = {p['id']: p['end'] for p in pieces}
    for members in groups.values():
        members.sort(key=lambda t: start[t])
        for x, y in zip(members, members[1:]):
            if end[x] < start[y]:
                pairs += 1
                joined += chain_of.get(x) is not None and chain_of.get(x) == chain_of.get(y)
    return {'links_with_both_labelled': labelled_links, 'confirmed': confirmed, 'conflicts': conflicts, 'chains_with_conflict': conflicting_chains,
            'true_consecutive_pairs': pairs, 'joined_true_pairs': int(joined)}


def synthetic_test(pieces, method, gaps, min_side=10.0, limit=40):
    """Cut a long piece into two with a gap and count how often the method joins the halves again. Returns {gap: (tests, joined back, joined to something else, unlinked)}."""
    out = {}
    for gap in gaps:
        tests = back = wrong = none = 0
        for idx, p in enumerate(pieces):
            if tests >= limit:
                break
            seconds = len(p['frames']) / FPS
            if seconds < 2 * min_side + gap:
                continue
            cut = len(p['frames']) // 2
            first_end = cut - int(gap * FPS / 2)
            second_start = cut + int(gap * FPS / 2)
            if first_end < min_side * FPS or len(p['frames']) - second_start < min_side * FPS:
                continue
            halves = []
            for sl in (slice(0, first_end), slice(second_start, None)):
                q = {k: (v[sl] if isinstance(v, np.ndarray) else v) for k, v in p.items()}
                summarise(q)
                halves.append(q)
            others = [o for k, o in enumerate(pieces) if k != idx]
            test_pieces = sorted(others + halves, key=lambda q: q['start'])
            i = next(k for k, q in enumerate(test_pieces) if q is halves[0])
            j = next(k for k, q in enumerate(test_pieces) if q is halves[1])
            links = dict(method(test_pieces))
            tests += 1
            if links.get(i) == j:
                back += 1
            elif i in links:
                wrong += 1
            else:
                none += 1
        out[gap] = (tests, back, wrong, none)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('tracks')
    parser.add_argument('camera')
    parser.add_argument('direction', type=int)
    parser.add_argument('bg')
    parser.add_argument('schedule')
    parser.add_argument('half')
    parser.add_argument('--max-gap', type=float, default=40.0)
    parser.add_argument('--out')
    parser.add_argument('--ratio', type=float, default=MAX_RATIO, help='a pair is possible when the relative distance is at most this many times the allowed distance')
    args = parser.parse_args()
    globals()['MAX_RATIO'] = args.ratio
    calibrations = json.loads((Path(args.store) / 'calibration' / 'calibrations.json').read_text(encoding='utf-8'))
    record = calibrations[args.camera]
    fitted = fit({**record, 'pitch': {**(record.get('pitch') or {}), 'length': 89, 'width': 62}})
    bg = tuple(float(v) for v in args.bg.split(',')) if args.bg else None
    schedule = parse_schedule(args.schedule) if args.schedule else []
    pieces, b_tracks, total = load_pieces(args.tracks, fitted, args.direction, bg, schedule)
    for p in pieces:
        summarise(p)
    print(f'{args.half}: team B tracks {b_tracks}, with metre rows and at least 10 rows {len(pieces)}')
    seconds = np.array([len(p['frames']) / FPS for p in pieces])
    print(f'  piece length (s): median {np.median(seconds):.0f}, 10th {np.percentile(seconds, 10):.0f}, 90th {np.percentile(seconds, 90):.0f}; tracks of 8 s or more {int((seconds >= 8).sum())}')
    base = alive_count(pieces, total)
    print(f'  alive pieces at one moment: median {int(np.median(base[base > 0]))}, max {int(base.max())}, moments above 11: {int((base > CAPACITY).sum())} frames')
    methods = {
        'V1 position only (Hungarian)': lambda ps: hungarian_links(ps, args.max_gap, False),
        'V2 position + line (Hungarian)': lambda ps: hungarian_links(ps, args.max_gap, True),
        'V3 position + line + capacity 11 (greedy)': lambda ps: greedy_links(ps, args.max_gap, True, CAPACITY, total),
    }
    human, auto, same_pairs, diff_pairs = human_truth(args.store, args.half)
    print(f'  human answers: {len(human)} tracks assigned by hand, {len(auto)} by number read by the computer, {len(same_pairs)} same-person pairs, {len(diff_pairs)} different-person pairs')
    report = {'half': args.half, 'tracks_b': b_tracks, 'pieces': len(pieces), 'methods': {}}
    for name, method in methods.items():
        links = method(pieces)
        chains = chains_from(links, len(pieces))
        span = span_count(chains, pieces, total)
        gaps = [(pieces[j]['start'] - pieces[i]['end']) / FPS for i, j in links]
        result = {'links': len(links), 'chains': len(chains), 'max_chains_alive': int(span.max()), 'frames_above_11': int((span > CAPACITY).sum()),
                  'gap_median_s': float(np.median(gaps)) if gaps else None, 'gap_under_1_6_s': int(sum(g <= 1.6 for g in gaps)),
                  'human': evaluate_human(chains, pieces, human, auto, same_pairs, diff_pairs, False),
                  'human_plus_computer_numbers': evaluate_human(chains, pieces, human, auto, same_pairs, diff_pairs, True)}
        result['synthetic'] = {str(g): v for g, v in synthetic_test(pieces, method, (5, 10, 20, 30)).items()}
        report['methods'][name] = result
        print(f'  {name}: links {result["links"]}, chains {result["chains"]} (pieces {len(pieces)}), max alive {result["max_chains_alive"]}, moments above 11 {result["frames_above_11"]}, median gap {result["gap_median_s"]}')
        print(f'    human truth: {result["human"]}')
        print(f'    with computer-read numbers: {result["human_plus_computer_numbers"]}')
        print(f'    synthetic cut (gap s: tests, joined back, joined elsewhere, unlinked): {result["synthetic"]}', flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
