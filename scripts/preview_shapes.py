"""Turn the detections of a team (about 8 to 10 of 11 per second, sometimes more because one player is found twice) into an 11-player shape (research helper, read only).

positions: the records of scripts/run_live_feedback.py --positions ({second: {'team': [[track, x, y]], 'other': [...]}}); x, y metres of the file.
For a block of BLOCK seconds all detections of one team are put into the frame of the team (x from its own goal 0..89, y with the team's right hand positive, the team attacking toward +x).
  * Detections near the own goal line are the goalkeeper; their mean is the keeper's place (assumed at the goal when fewer than MIN_GK_POINTS are seen: marked as filled).
  * The other detections are grouped into 10 places with k-means (k-means++ start, several restarts). A player found twice falls into the same group; a player missed in one second but seen in another second of the block
    is still one group, so the 11 places do not depend on how many were found in a single second.
  * The 10 places are cut into lines by depth with app.team_formation.best_lines (3 lines, or 4 when that explains clearly more) and named from the defence to the attack, left to right.
At a single second (a goal moment) the detections are matched to the 11 places of the block around that second; places nobody was matched to are filled at the place of the block moved by the average offset
of the matched ones, and extra detections (more than 11) are dropped. Filled places are returned with filled=True so that a drawing can show them as an estimate.
This describes the shape the team had over about half a minute. It is not a lineup and not who stood where.
"""
import math
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.team_formation import FOUR_LINES_GAIN  # noqa: E402

L, W = 89.0, 62.0
BLOCK = 30
MIN_POINTS = 100
MIN_GK_POINTS = 8
GK_ZONE = (12.0, 14.0)             # x from the own goal line, |y|
LINE_NAMES = {3: ('D', 'M', 'F'), 4: ('D', 'M', 'A', 'F')}


def frame(x, y, direction):
    return x * direction + L / 2, y * direction


def kmeans(points, k, restarts=10, iterations=40, seed=1):
    rng = random.Random(seed)
    best = None
    for _ in range(restarts):
        centres = [rng.choice(points)]
        while len(centres) < k:
            weights = [min((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 for c in centres) for p in points]
            if sum(weights) == 0:
                centres.append(rng.choice(points))
                continue
            centres.append(rng.choices(points, weights=weights)[0])
        for _ in range(iterations):
            groups = [[] for _ in centres]
            for p in points:
                groups[min(range(k), key=lambda i: (p[0] - centres[i][0]) ** 2 + (p[1] - centres[i][1]) ** 2)].append(p)
            moved = [(statistics.mean(q[0] for q in g), statistics.mean(q[1] for q in g)) if g else centres[i] for i, g in enumerate(groups)]
            if moved == centres:
                break
            centres = moved
        inertia = sum(min((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 for c in centres) for p in points)
        if best is None or inertia < best[0]:
            best = (inertia, centres)
    return best[1]


LIMITS = {3: ((3, 5), (2, 5), (1, 4)), 4: ((3, 5), (1, 4), (1, 3), (1, 3))}      # players per line: a team does not play with one defender or with six in midfield


def _constrained_lines(depths, lines):
    """Sorted depths -> (error, counts) of the best cut into `lines` groups within LIMITS, or None."""
    n = len(depths)
    best = None

    def walk(start, index, counts):
        nonlocal best
        if index == lines - 1:
            rest = n - start
            low, high = LIMITS[lines][index]
            if low <= rest <= high:
                parts = counts + [rest]
                error, at = 0.0, 0
                for size in parts:
                    group = depths[at:at + size]
                    mean = sum(group) / size
                    error += sum((x - mean) ** 2 for x in group)
                    at += size
                if best is None or error < best[0]:
                    best = (error, parts)
            return
        low, high = LIMITS[lines][index]
        for size in range(low, high + 1):
            if start + size < n:
                walk(start + size, index + 1, counts + [size])
    walk(0, 0, [])
    return best


def name_lines(places):
    """10 places (x, y) -> (formation text such as '4-4-2', [(label, x, y)]) from the defence to the attack, each line from the team's left to its right."""
    ordered = sorted(places)
    depths = [p[0] for p in ordered]
    three = _constrained_lines(depths, 3)
    four = _constrained_lines(depths, 4)
    counts = four[1] if four and three and four[0] <= FOUR_LINES_GAIN * three[0] else three[1]
    names = LINE_NAMES[len(counts)]
    out, start = [], 0
    for name, n in zip(names, counts):
        line = sorted(ordered[start:start + n], key=lambda p: p[1])
        out += [(f'{name}{i + 1}', x, y) for i, (x, y) in enumerate(line)]
        start += n
    return '-'.join(str(n) for n in counts), out


def split_points(records, key, direction):
    gk, field = [], []
    for r in records:
        for _t, x, y in r[key]:
            fx, fy = frame(x, y, direction)
            (gk if fx < GK_ZONE[0] and abs(fy) < GK_ZONE[1] else field).append((fx, fy))
    return gk, field


def kmeans1d(values, k, restarts=6, iterations=40):
    """Values -> (sorted centres, group index per value, inertia); the start is spread over the quantiles, so the result is the same on every run."""
    ordered = sorted(values)
    best = None
    for r in range(restarts):
        shift = (r - restarts / 2) * 0.03
        centres = [ordered[min(len(ordered) - 1, max(0, int(len(ordered) * min(0.98, max(0.02, (i + 0.5) / k + shift)))))] for i in range(k)]
        for _ in range(iterations):
            groups = [min(range(k), key=lambda i: abs(v - centres[i])) for v in values]
            moved = []
            for i in range(k):
                members = [v for v, g in zip(values, groups) if g == i]
                moved.append(statistics.mean(members) if members else centres[i])
            if moved == centres:
                break
            centres = moved
        groups = [min(range(k), key=lambda i: abs(v - centres[i])) for v in values]
        inertia = sum((v - centres[g]) ** 2 for v, g in zip(values, groups))
        if best is None or inertia < best[2]:
            best = (centres, groups, inertia)
    order = sorted(range(k), key=lambda i: best[0][i])
    rank = {old: new for new, old in enumerate(order)}
    return [best[0][i] for i in order], [rank[g] for g in best[1]], best[2]


def players_per_line(sizes, limits, total=10):
    """Shares of the detections of each line -> whole players per line (sum = total, largest remainders, then moved into the limits)."""
    raw = [total * n / sum(sizes) for n in sizes]
    counts = [int(r) for r in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - counts[i], reverse=True)[:total - sum(counts)]:
        counts[i] += 1
    for _ in range(20):
        low = next((i for i, c in enumerate(counts) if c < limits[i][0]), None)
        high = next((i for i, c in enumerate(counts) if c > limits[i][1]), None)
        if low is None and high is None:
            break
        if low is not None:
            donor = max((i for i in range(len(counts)) if counts[i] > limits[i][0]), key=lambda i: counts[i], default=None)
            if donor is None:
                break
            counts[donor] -= 1
            counts[low] += 1
        else:
            taker = min((i for i in range(len(counts)) if counts[i] < limits[i][1]), key=lambda i: counts[i], default=None)
            if taker is None:
                break
            counts[high] -= 1
            counts[taker] += 1
    return counts


def shape_of(records, key, direction):
    """One block -> {'gk': (x, y, filled), 'places': [(label, x, y)], 'text': '4-4-2', 'depth': mean depth, 'points': n} or None.
    The number of players of a line is the share of all detections that fell into the line (times 10), so a part of the pitch where players are found more often does not get more players."""
    gk_points, field = split_points(records, key, direction)
    if len(field) < MIN_POINTS:
        return None
    depths = [p[0] for p in field]
    centres3, groups3, error3 = kmeans1d(depths, 3)
    centres4, groups4, error4 = kmeans1d(depths, 4)
    lines, groups = (4, groups4) if error4 <= FOUR_LINES_GAIN * error3 else (3, groups3)
    members = [[field[i] for i in range(len(field)) if groups[i] == g] for g in range(lines)]
    counts = players_per_line([max(1, len(m)) for m in members], LIMITS[lines])
    labelled = []
    for name, group, n in zip(LINE_NAMES[lines], members, counts):
        if not group:
            continue
        if n == 1:
            spots = [(statistics.mean(q[0] for q in group), statistics.mean(q[1] for q in group))]
        else:
            centres, parts, _e = kmeans1d([q[1] for q in group], n)
            spots = []
            for i in range(n):
                part = [q for q, g in zip(group, parts) if g == i]
                spots.append((statistics.mean(q[0] for q in part), statistics.mean(q[1] for q in part)) if part else (statistics.mean(q[0] for q in group), centres[i]))
        labelled += [(f'{name}{i + 1}', x, y) for i, (x, y) in enumerate(sorted(spots, key=lambda t: t[1]))]
    text = '-'.join(str(n) for n in counts)
    gk = (statistics.mean(p[0] for p in gk_points), statistics.mean(p[1] for p in gk_points), False) if len(gk_points) >= MIN_GK_POINTS else (6.0, 0.0, True)
    return {'gk': gk, 'places': labelled, 'text': text, 'depth': statistics.mean(x for _l, x, _y in labelled), 'points': len(field)}


def blocks_of(seconds, key, direction, block=BLOCK):
    """{second: record} -> [{'from': t0, ...shape...}] one per non-overlapping block."""
    if not seconds:
        return []
    first, last = min(seconds), max(seconds)
    out = []
    for t0 in range(first - first % block, last + 1, block):
        records = [seconds[s] for s in range(t0, t0 + block) if s in seconds]
        shape = shape_of(records, key, direction)
        if shape:
            shape['from'] = t0
            out.append(shape)
    return out


def average_shape(blocks):
    """Blocks of the most common formation text -> (text, share, {label: (x, y)}, gk (x, y)) averaged place by place."""
    if not blocks:
        return None
    counts = Counter(b['text'] for b in blocks)
    text, n = counts.most_common(1)[0]
    chosen = [b for b in blocks if b['text'] == text]
    labels = [lab for lab, _x, _y in chosen[0]['places']]
    pos = {lab: (statistics.mean(dict((l, (x, y)) for l, x, y in b['places'])[lab][0] for b in chosen), statistics.mean(dict((l, (x, y)) for l, x, y in b['places'])[lab][1] for b in chosen)) for lab in labels}
    gk = (statistics.mean(b['gk'][0] for b in chosen), statistics.mean(b['gk'][1] for b in chosen))
    return text, n / len(blocks), len(blocks), pos, gk


def merge_doubles(points, wanted=11):
    """More detections than players: the two closest ones are one player found twice, they become their middle, until `wanted` are left."""
    points = list(points)
    while len(points) > wanted:
        i, j = min(((i, j) for i in range(len(points)) for j in range(i + 1, len(points))),
                   key=lambda ij: math.hypot(points[ij[0]][0] - points[ij[1]][0], points[ij[0]][1] - points[ij[1]][1]))
        middle = ((points[i][0] + points[j][0]) / 2, (points[i][1] + points[j][1]) / 2)
        points = [q for k, q in enumerate(points) if k not in (i, j)] + [middle]
    return points


def eleven_at(seconds, second, key, direction, around=15):
    """The 11 players at one second: ([(x, y, filled)], number of doubles merged, formation text of the block) or None when the block around has no shape.
    More than 11 detections: the closest ones are merged. Fewer: the missing players are put at the places of the block that nobody was found at, moved by the average offset of the found ones."""
    records = [seconds[s] for s in range(second - around, second + around + 1) if s in seconds]
    shape = shape_of(records, key, direction)
    now = seconds.get(second)
    if not shape or not now:
        return None
    targets = [(shape['gk'][0], shape['gk'][1])] + [(x, y) for _l, x, y in shape['places']]
    raw = [frame(x, y, direction) for _t, x, y in now[key]]
    detections = merge_doubles(raw)
    pairs = sorted(((math.hypot(d[0] - t[0], d[1] - t[1]), i, j) for i, d in enumerate(detections) for j, t in enumerate(targets)))
    used_d, used_t, offsets = set(), set(), []
    for dist, i, j in pairs:
        if i in used_d or j in used_t or dist > 25.0:
            continue
        used_d.add(i)
        used_t.add(j)
        offsets.append((detections[i][0] - targets[j][0], detections[i][1] - targets[j][1]))
    out = [(x, y, False) for x, y in detections]
    missing = 11 - len(detections)
    if missing > 0:
        dx = statistics.mean(o[0] for o in offsets) if offsets else 0.0
        dy = statistics.mean(o[1] for o in offsets) if offsets else 0.0
        free = [t for j, t in enumerate(targets) if j not in used_t]
        free.sort(key=lambda t: -min((math.hypot(t[0] + dx - d[0], t[1] + dy - d[1]) for d in detections), default=0.0))
        for x, y in free[:missing]:
            out.append((min(L, max(0.0, x + dx)), max(-W / 2, min(W / 2, y + dy)), True))
    return out, len(raw) - len(detections), shape['text']
