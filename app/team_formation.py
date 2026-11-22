"""Formation and space control of a team from player positions only (no ball, no names, no new labels).

Positions are metres in the frame of app/team_tactics.py: u grows towards the goal the team attacks, v is across the pitch with the team's own left negative.

Formation: the outfield players of one moment are cut into lines by depth (`u`). The cut that minimises the squared distance of the players to their line mean is found
exactly (dynamic programming on the sorted depths), for three and for four lines; the four-line cut is used only when it explains clearly more than the three-line cut.
The answer is the number of players per line, from the defence to the attack, for example "4-4-2". It describes where the players stood in that second, not a plan:
a team that defends deep with eight behind the ball shows a different string than the one it attacks with. A moment with fewer than 9 outfield players seen has no answer.
Measured on this match (team B, 30 s blocks, 5 min windows): the most common answer of a window covers only 10 to 30 % of its blocks, so the formation text is NOT stable enough
to be reported as 'the formation of the team'. Use it as a per-block description only; the stable numbers are the space control and the line depths of app/team_tactics.py.

Space control: every cell of a grid over the pitch is given to the team whose nearest player would get there first (distance / running speed), softened so that
a cell reached at nearly the same time by both teams counts as half. It is a model of reach, not of who has the ball, and it uses positions only (no speeds), so
the share of a team is the share of the pitch that its players are closer to, corrected a little for a position at the edge.
"""
import math

from app.goalkeeper import without_goalkeeper

PITCH_LENGTH, PITCH_WIDTH = 89.0, 62.0
RUN_SPEED = 5.0              # m/s used for the time to reach a cell
SOFTNESS = 0.45              # seconds: a difference of this size gives a 73/27 split of a cell
MIN_OUTFIELD = 9
FOUR_LINES_GAIN = 0.45       # the four-line cut must leave at most this share of the three-line error


def _split_error(values, cuts):
    error = 0.0
    bounds = [0, *cuts, len(values)]
    for a, b in zip(bounds, bounds[1:]):
        part = values[a:b]
        mean = sum(part) / len(part)
        error += sum((x - mean) ** 2 for x in part)
    return error


def best_lines(values, lines):
    """Sorted depths -> (error, counts per line) of the best cut into `lines` non-empty groups."""
    n = len(values)
    if n < lines:
        return None
    best = None
    if lines == 3:
        candidates = ((a, b) for a in range(1, n - 1) for b in range(a + 1, n))
    elif lines == 4:
        candidates = ((a, b, c) for a in range(1, n - 2) for b in range(a + 1, n - 1) for c in range(b + 1, n))
    else:
        raise ValueError('lines must be 3 or 4')
    for cuts in candidates:
        error = _split_error(values, cuts)
        if best is None or error < best[0]:
            best = (error, cuts)
    bounds = [0, *best[1], n]
    return best[0], [b - a for a, b in zip(bounds, bounds[1:])]


def formation(points):
    """[(u, v)] of one team at one moment -> {'text': '4-4-2', 'counts': [4, 4, 2], 'goalkeeper_removed': bool} or None.
    The goalkeeper is taken out first: the deepest player when he stands 8 m or more behind the next one, or, when 11 are seen, the deepest one."""
    ordered = sorted(points)
    removed = False
    ordered, removed = _without_goalkeeper(ordered)
    if len(ordered) < MIN_OUTFIELD:
        return None
    return _formation_of_depths([u for u, _ in ordered], removed)


def _without_goalkeeper(ordered):
    return without_goalkeeper(ordered)


def _formation_of_depths(depths, removed=False):
    three = best_lines(depths, 3)
    four = best_lines(depths, 4)
    chosen = four if four and three and three[0] > 0 and four[0] <= FOUR_LINES_GAIN * three[0] else three
    if chosen[1][0] == 1 and not removed and len(depths) >= 10:
        # a line of one player at the back is the goalkeeper that stood closer than 5 m behind the defence: take him out and cut the rest again
        return _formation_of_depths(depths[1:], True)
    return {'text': '-'.join(str(c) for c in chosen[1]), 'counts': chosen[1], 'goalkeeper_removed': removed}


def formation_blocks(series, key='ours_points', block=30):
    """One answer per `block` seconds: the depths of the outfield players are averaged rank by rank over the seconds of the block that show the usual number of
    outfield players, and the averaged depths are cut into lines. This smooths the one-second noise (a player not seen, a player stepping out of the line).
    Returns [(first second, formation text, seconds used)]."""
    blocks = {}
    for second, row in sorted(series.items()):
        ordered, _ = _without_goalkeeper(sorted(row[key]))
        if len(ordered) >= MIN_OUTFIELD:
            blocks.setdefault(second // block, []).append([u for u, _ in ordered])
    out = []
    for b, rows in sorted(blocks.items()):
        sizes = {}
        for r in rows:
            sizes[len(r)] = sizes.get(len(r), 0) + 1
        size = max(sizes, key=lambda k: (sizes[k], k))
        same = [r for r in rows if len(r) == size]
        if len(same) < 5:
            continue
        depths = [sum(r[i] for r in same) / len(same) for i in range(size)]
        out.append((b * block, _formation_of_depths(depths)['text'], len(same)))
    return out


def formation_by_window(series, length=300, key='ours_points'):
    """series as made by app.team_tactics.seconds_series -> [(first second, most common formation, share of the answered seconds, answered seconds, second most common)]."""
    windows = {}
    for second, row in series.items():
        answer = formation(row[key])
        if answer is not None:
            windows.setdefault(second // length, []).append(answer['text'])
    out = []
    for w, texts in sorted(windows.items()):
        counts = {}
        for t in texts:
            counts[t] = counts.get(t, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        out.append((w * length, ranked[0][0], ranked[0][1] / len(texts), len(texts), ranked[1][0] if len(ranked) > 1 else None))
    return out


def formation_summary(blocks, length=300):
    """formation_blocks output -> [(first second, most common formation, share of the blocks, blocks counted, second most common)] per window of `length` seconds."""
    windows = {}
    for start, text, _n in blocks:
        windows.setdefault(start // length, []).append(text)
    out = []
    for w, texts in sorted(windows.items()):
        counts = {}
        for t in texts:
            counts[t] = counts.get(t, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        out.append((w * length, ranked[0][0], ranked[0][1] / len(texts), len(texts), ranked[1][0] if len(ranked) > 1 else None))
    return out


def control_grid(ours, theirs, columns=18, rows=12, pitch_length=PITCH_LENGTH, pitch_width=PITCH_WIDTH):
    """Share of every cell controlled by our team, rows from our own goal line (row 0) to the opponent's (last row), columns from our left to our right.
    `ours` and `theirs` are [(u, v)] in the frame of ours (theirs already turned into it). Returns None when either team has fewer than 5 players."""
    if len(ours) < 5 or len(theirs) < 5:
        return None
    grid = []
    for r in range(rows):
        u = -pitch_length / 2 + (r + 0.5) * pitch_length / rows
        line = []
        for c in range(columns):
            v = -pitch_width / 2 + (c + 0.5) * pitch_width / columns
            ours_time = min(math.hypot(u - pu, v - pv) for pu, pv in ours) / RUN_SPEED
            theirs_time = min(math.hypot(u - pu, v - pv) for pu, pv in theirs) / RUN_SPEED
            line.append(1.0 / (1.0 + math.exp(-(theirs_time - ours_time) / SOFTNESS)))
        grid.append(line)
    return grid


def control_summary(grid):
    """Grid -> total share of our team, and the share in the own, middle and opponent third (None for a missing grid)."""
    if not grid:
        return None
    rows = len(grid)
    thirds = [grid[i * rows // 3:(i + 1) * rows // 3] for i in range(3)]
    mean = lambda block: sum(sum(r) for r in block) / sum(len(r) for r in block)
    return {'total': mean(grid), 'own_third': mean(thirds[0]), 'middle_third': mean(thirds[1]), 'opponent_third': mean(thirds[2])}


def control_series(series, step=1):
    """seconds_series output -> {second: control_summary} with the opponent turned into our frame (u and v negated)."""
    out = {}
    for second, row in series.items():
        if second % step:
            continue
        theirs = [(-u, -v) for u, v in row['theirs_points']]
        summary = control_summary(control_grid(row['ours_points'], theirs))
        if summary is not None:
            out[second] = summary
    return out


def control_by_window(controls, length=300):
    """control_series output -> [(first second, mean total, mean opponent third, seconds counted)]."""
    windows = {}
    for second, c in controls.items():
        windows.setdefault(second // length, []).append(c)
    return [(w * length, sum(c['total'] for c in rows) / len(rows), sum(c['opponent_third'] for c in rows) / len(rows), len(rows)) for w, rows in sorted(windows.items())]
