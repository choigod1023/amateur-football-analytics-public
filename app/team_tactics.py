"""Team level tactics from the player positions of one camera, without the ball and without any player's name.

Positions are metres on the pitch. `by_frame[frame][team] = [(track id, x, y)]` as made by `metre_rows` (x along the pitch, y across, camera on the +y side). A team's own
attack direction `d` (+1 or -1) turns x into `u = x * d`: u grows towards the goal the team attacks, so u = -44.5 is its own goal line. y is mirrored for the team that attacks
the other way, so that 'left' and 'right' are always the team's own left and right.

What the numbers are, and are not:
  * Only the players the tracker followed count (about 10 of 11 per team on the sampled seconds). Counts and spreads come from those; the goalkeeper is counted when seen.
  * Without the ball nothing here says who had it. 'Territory' is the share of seconds the team's centre stood in the opponent half; it is not possession.
  * Distances and speeds come from one second apart, positions are as good as the pitch calibration.
"""
import math

from app.goalkeeper import without_goalkeeper

PITCH_LENGTH, PITCH_WIDTH = 89.0, 62.0
MIN_PLAYERS = 7                                  # a second with fewer players of a team seen says too little about its shape


def oriented(players, direction, mirror):
    """[(id, u, v)] of one team: u towards the goal it attacks, v across (left negative for the team's own view when mirror is True)."""
    return [(tid, x * direction, y * (direction if mirror else 1.0)) for tid, x, y in players]


def _percentile(values, share):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, int(round(share * (len(values) - 1)))))]


def hull_area(points):
    """Area of the convex hull of (u, v) points in square metres (0 for fewer than 3 points)."""
    pts = sorted(set((round(u, 3), round(v, 3)) for u, v in points))
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
    return abs(sum(hull[i][0] * hull[(i + 1) % len(hull)][1] - hull[(i + 1) % len(hull)][0] * hull[i][1] for i in range(len(hull)))) / 2


def shape(points):
    """The shape of a team at one moment: players [(u, v)] -> dict, or None when fewer than MIN_PLAYERS are seen.

    depth: distance from the deepest to the most advanced outfield player (the deepest player is skipped when he stands 8 m or more behind the next one: the goalkeeper);
    width: spread across the pitch, 10th to 90th percentile; back/front: mean of the two deepest / two most advanced outfield players; area: convex hull;
    lines: the outfield players split into three groups by depth (defence, midfield, attack) and the mean u of each; gaps: distance between the group means."""
    if len(points) < MIN_PLAYERS:
        return None
    ordered, _ = without_goalkeeper(points)
    us =[u for u, _ in ordered]
    vs = [v for _, v in ordered]
    n = len(ordered)
    cut1, cut2 = n // 3, n - n // 3
    groups = [us[:cut1] or us[:1], us[cut1:cut2] or us[:1], us[cut2:] or us[-1:]]
    lines = [sum(g) / len(g) for g in groups]
    return {'n': len(points), 'centre_u': sum(us) / n, 'centre_v': sum(vs) / n, 'depth': us[-1] - us[0], 'width': _percentile(vs, 0.9) - _percentile(vs, 0.1),
            'back': sum(us[:2]) / 2, 'front': sum(us[-2:]) / 2, 'area': hull_area(ordered_pairs(ordered)), 'lines': lines, 'gaps': [lines[1] - lines[0], lines[2] - lines[1]]}


def ordered_pairs(ordered):
    return [(u, v) for u, v in ordered]


def seconds_series(by_frame, team, other, direction, fps, frames, mirror_team=True):
    """{second: {'ours': shape or None, 'theirs': shape or None, 'ours_points': [...], 'theirs_points': [...]}} for the team `team` (attacking `direction`) and its opponent `other`."""
    step = max(1, int(round(fps)))
    out = {}
    for frame in range(0, frames, step):
        teams = by_frame.get(frame) or {}
        ours = [(u, v) for _, u, v in oriented(teams.get(team, []), direction, True)]
        theirs = [(u, v) for _, u, v in oriented(teams.get(other, []), -direction, True)]
        out[frame // step] = {'ours': shape(ours), 'theirs': shape(theirs), 'ours_points': ours, 'theirs_points': theirs}
    return out


def windows(series, length=300, key='ours', field=None):
    """Average of a shape field per window of `length` seconds: [(first second, mean, seconds counted)]."""
    out = {}
    for second, row in series.items():
        s = row[key]
        if s is None:
            continue
        value = s[field] if isinstance(field, str) else field(s)
        w = second // length
        total, count = out.get(w, (0.0, 0))
        out[w] = (total + value, count + 1)
    return [(w * length, total / count, count) for w, (total, count) in sorted(out.items())]


def zone_shares(series, key='ours_points', pitch_length=PITCH_LENGTH, pitch_width=PITCH_WIDTH):
    """3 x 3 share of the player-seconds: rows are depth thirds (own third, middle, opponent third), columns left, centre, right (the team's own view)."""
    grid = [[0] * 3 for _ in range(3)]
    for row in series.values():
        for u, v in row[key]:
            r = min(2, max(0, int((u + pitch_length / 2) / pitch_length * 3)))
            c = min(2, max(0, int((v + pitch_width / 2) / pitch_width * 3)))
            grid[r][c] += 1
    total = sum(sum(r) for r in grid) or 1
    return [[round(100.0 * x / total, 1) for x in r] for r in grid]


def territory(series):
    """Share of the seconds with enough players in which the centre of the team stood beyond the middle line, in per cent."""
    values = [row['ours']['centre_u'] for row in series.values() if row['ours']]
    return round(100.0 * sum(1 for u in values if u > 0) / len(values), 1) if values else None


def activity(by_frame, team, fps, frames, window=5):
    """Mean speed of the tracked players of a team per second: {second: metres per second}. Speed is the straight distance covered over `window` frames; jumps above 9 m/s are dropped."""
    step = max(1, int(round(fps)))
    last = {}
    out = {}
    for frame in range(0, frames):
        now = {tid: (x, y) for tid, x, y in (by_frame.get(frame) or {}).get(team, [])}
        past = {tid: (x, y) for tid, x, y in (by_frame.get(frame - window) or {}).get(team, [])} if frame >= window else {}
        speeds = []
        for tid, (x, y) in now.items():
            if tid in past:
                v = math.hypot(x - past[tid][0], y - past[tid][1]) * fps / window
                if v <= 9.0:
                    speeds.append(v)
        if speeds and frame % step == 0:
            out[frame // step] = sum(speeds) / len(speeds)
    return out


def tightness(series, direction=1):
    """For the opponent's players: the mean distance to the nearest player of ours per second (smaller means closer marking or pressing), over the seconds with enough players."""
    out = {}
    for second, row in series.items():
        if len(row['ours_points']) < MIN_PLAYERS or len(row['theirs_points']) < MIN_PLAYERS:
            continue
        # both lists are oriented to their own team: bring the opponents into our view (u and v flipped)
        theirs = [(-u, -v) for u, v in row['theirs_points']]
        ds = [min(math.hypot(u - a, v - b) for a, b in row['ours_points']) for u, v in theirs]
        out[second] = sum(ds) / len(ds)
    return out


def surges(series, window=6, distance=12.0, minimum_gap=20):
    """Moments where the centre of the team moved at least `distance` metres forward (a surge) or backward (a retreat) within `window` seconds: [(second, 'forward' or 'back', metres)].
    One entry per `minimum_gap` seconds, the strongest."""
    centre = {s: r['ours']['centre_u'] for s, r in series.items() if r['ours']}
    found = []
    for s in sorted(centre):
        t = s + window
        if t in centre:
            d = centre[t] - centre[s]
            if abs(d) >= distance:
                found.append((s, 'forward' if d > 0 else 'back', round(d, 1)))
    picked = []
    for item in sorted(found, key=lambda x: -abs(x[2])):
        if all(abs(item[0] - p[0]) >= minimum_gap for p in picked):
            picked.append(item)
    return sorted(picked)


def open_side(series, key='ours_points', defenders=4):
    """How often a team's back line leaves a side of the pitch uncovered. For every second with enough players the `defenders` deepest outfield players are taken (the goalkeeper
    is skipped when he stands 8 m or more behind the next player) and the pitch is cut into three lanes of equal width (left, centre, right, the team's own view). The result is the share
    of the counted seconds in which none of those players stood in the lane: {'left': %, 'centre': %, 'right': %} or None."""
    counted, empty = 0, {'left': 0, 'centre': 0, 'right': 0}
    for row in series.values():
        pts = sorted(row[key])
        if len(pts) < MIN_PLAYERS:
            continue
        pts, _ = without_goalkeeper(pts)
        deep = pts[:defenders]
        counted += 1
        for name, low, high in (('left', -PITCH_WIDTH / 2, -PITCH_WIDTH / 6), ('centre', -PITCH_WIDTH / 6, PITCH_WIDTH / 6), ('right', PITCH_WIDTH / 6, PITCH_WIDTH / 2)):
            if not any(low <= v < high for _, v in deep):
                empty[name] += 1
    return {k: round(100.0 * v / counted, 1) for k, v in empty.items()} if counted else None
