"""Join broken person tracks of one short clip. Image space only: positions are pixels, not metres.

A track that ends and another that starts a few frames later close to where the first one was heading are treated as
one person when their team labels do not contradict each other. The joins are proposals from a distance rule;
nothing here was checked against human labels, so the result is reported as a count of joins, never as accuracy.
"""
import math
import statistics
from collections import Counter

MAX_GAP = 8                     # frames; 8 frames are 1.6 s at 5 fps
SPEED_FACTOR = 0.5              # allowed travel per missing frame, in box heights
BASE_FACTOR = 0.8               # allowed offset even without a gap, in box heights


def _centre(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _height(box):
    return max(1.0, box[3] - box[1])


def _team(rows):
    teams = {row['team'] for row in rows if row['team'] not in (None, 'S')}
    return teams.pop() if len(teams) == 1 else None


def _velocity(rows):
    tail = rows[-3:]
    if len(tail) < 2:
        return (0.0, 0.0)
    (x0, y0), (x1, y1) = _centre(tail[0]['box']), _centre(tail[-1]['box'])
    frames = max(1, tail[-1]['frame'] - tail[0]['frame'])
    return ((x1 - x0) / frames, (y1 - y0) / frames)


LONG_GAP = 8                    # from this gap on the allowed travel is capped (see _cost)
MAX_TRAVEL = 6.0                # box heights; a player is not 6 body heights away after a few seconds without a detection


def _cost(first, second, max_gap, max_overlap=0):
    gap = second[0]['frame'] - first[-1]['frame']
    if gap < 1 - max_overlap or gap > max_gap:
        return None
    gap = max(gap, 1)                                                        # an overlap of a few frames counts as a gap of one
    team_a, team_b = _team(first), _team(second)
    if team_a and team_b and team_a != team_b:
        return None
    vx, vy = _velocity(first)
    cx, cy = _centre(first[-1]['box'])
    px, py = cx + vx * gap, cy + vy * gap
    nx, ny = _centre(second[0]['box'])
    height = (_height(first[-1]['box']) + _height(second[0]['box'])) / 2
    distance = math.hypot(nx - px, ny - py)
    allowed = height * min(BASE_FACTOR + SPEED_FACTOR * gap, MAX_TRAVEL) if gap > LONG_GAP else height * (BASE_FACTOR + SPEED_FACTOR * gap)
    return distance / allowed if distance <= allowed else None


def _observed_endpoint(rows, start=False):
    """Ignore interpolated tails and a collapsed terminal box for matching only.

    A detector may abruptly crop a standing player's box to his feet. Velocity
    from that box sends the next prediction sideways. At most two consecutive
    collapsed observed boxes are skipped; longer losses stay unresolved.
    """
    observed = [r for r in rows if not any(r.get(k) for k in ('interpolated', 'estimated', 'predicted'))]
    edge = observed[:9] if start else observed[-9:]
    if len(edge) < 3:
        return observed
    typical = statistics.median(_height(r['box']) for r in edge)
    for _ in range(2):
        index = 0 if start else -1
        if len(observed) < 3 or _height(observed[index]['box']) >= typical * .6:
            break
        observed = observed[1:] if start else observed[:-1]
    return observed


def _evidence_cost(first, second, max_gap, max_overlap=0):
    a, b = _observed_endpoint(first), _observed_endpoint(second, True)
    return _endpoint_cost(a, b, max_gap, max_overlap)


def _endpoint_cost(a, b, max_gap, max_overlap):
    if not a or not b:
        return None
    gap = b[0]['frame'] - a[-1]['frame']
    if gap < 1 - max_overlap or gap > max_gap:
        return None
    # A simultaneous observation at two distinct boxes is not a birth backfill.
    shared = {r['frame']: r for r in a}
    overlap = [(shared[r['frame']]['box'], r['box']) for r in b if r['frame'] in shared]
    if overlap and any(_overlap_share(x, y) < .5 for x, y in overlap):
        return None
    return _cost(a, b, max_gap, max_overlap)


def _local_team(rows):
    """A strong endpoint vote, not a verified team identity; unknown votes count against it."""
    if len(rows) < 3:
        return None
    votes = Counter(r.get('team') for r in rows if r.get('team') in ('A', 'B', 'R'))
    if not votes:
        return None
    team, count = votes.most_common(1)[0]
    return team if count / len(rows) >= .8 else None


def stitch_tracks(tracks, max_gap=MAX_GAP, max_overlap=0, *, different_pairs=(), require_mutual=False, ambiguity_margin=0.15, endpoint_evidence=False, endpoint_team_guard=False, membership=None):
    """tracks: {id: [{'frame', 'team', 'box'} ...]} sorted by frame. Returns (new tracks, number of joins).

    Optional `different_pairs` forbids a human-rejected pair even through a chain.
    Optional `membership` receives source id -> output id for every nonempty
    input piece, including pieces entirely consumed by overlap deduplication.
    `require_mutual` accepts only unambiguous best matches in both directions and
    checks component-wide temporal conflicts. `ambiguity_margin` is in normalized
    distance cost units, not a calibrated probability. Defaults preserve legacy behavior.

    A joined track keeps the id of its first piece. Each piece joins at most one predecessor and one successor, and
    pieces that overlap in time are never joined, except by at most `max_overlap` frames (the births that scripts/track_from_cache.py adds back a few frames before a track
    can overlap the end of its predecessor); the frames of the later piece that the earlier one already holds are dropped.
    """
    # Constraints are explicit human negatives, not evaluation labels. They apply
    # across whole components so A-B and B-C cannot bypass an A-C rejection.
    forbidden = {frozenset((str(a), str(b))) for a, b in different_pairs}
    if membership is not None:
        membership.clear()
    ordered = {tid: sorted(rows, key=lambda r: r['frame']) for tid, rows in tracks.items() if rows}
    tails = {tid: _observed_endpoint(rows) for tid, rows in ordered.items()} if endpoint_evidence or endpoint_team_guard else {}
    heads = {tid: _observed_endpoint(rows, True) for tid, rows in ordered.items()} if endpoint_evidence or endpoint_team_guard else {}
    end_teams = {tid: _local_team(rows[-5:]) for tid, rows in tails.items()} if endpoint_team_guard else {}
    start_teams = {tid: _local_team(rows[:5]) for tid, rows in heads.items()} if endpoint_team_guard else {}
    pairs = []
    for a, first in ordered.items():
        for b, second in ordered.items():
            if a == b:
                continue
            if endpoint_team_guard and end_teams[a] and start_teams[b] and end_teams[a] != start_teams[b]:
                continue
            cost = _endpoint_cost(tails[a], heads[b], max_gap, max_overlap) if endpoint_evidence else _cost(first, second, max_gap, max_overlap)
            if cost is not None:
                pairs.append((cost, a, b))
    pairs.sort()
    outgoing, incoming = {}, {}
    for cost, a, b in pairs:
        outgoing.setdefault(a, []).append((cost, b))
        incoming.setdefault(b, []).append((cost, a))

    def clear_best(candidates, target):
        return (candidates[0][1] == target and
                (len(candidates) == 1 or candidates[1][0] - candidates[0][0] > ambiguity_margin))

    members = {tid: {tid} for tid in ordered}
    successor, predecessor = {}, {}
    for _, a, b in pairs:
        if require_mutual and not (clear_best(outgoing[a], b) and clear_best(incoming[b], a)):
            continue
        left, right = members[a], members[b]
        if any(frozenset((str(x), str(y))) in forbidden for x in left for y in right):
            continue
        if require_mutual:
            # Checking only the two endpoints can hide an overlap elsewhere in a chain.
            if any(min(ordered[x][-1]['frame'], ordered[y][-1]['frame']) -
                   max(ordered[x][0]['frame'], ordered[y][0]['frame']) + 1 > max_overlap
                   for x in left for y in right):
                continue
        if a in successor or b in predecessor:
            continue
        # a chain must not turn back on itself
        end = b
        while end in successor:
            end = successor[end]
        if end == a:
            continue
        successor[a] = b
        predecessor[b] = a
        combined = left | right
        for member in combined:
            members[member] = combined
    result, joins = {}, len(successor)
    for tid in ordered:
        if tid in predecessor:
            continue
        rows, current = list(ordered[tid]), tid
        if membership is not None:
            membership[current] = tid
        while current in successor:
            current = successor[current]
            if membership is not None:
                membership[current] = tid
            rows.extend(r for r in ordered[current] if r['frame'] > rows[-1]['frame'])
        result[tid] = rows
    return result, joins


def fill_gaps(tracks, max_gap=MAX_GAP, avoid_covered=False, cover=0.6):
    """Add the frames a track lost between two sightings by straight-line interpolation of its box.

    Only gaps of at most `max_gap` frames are filled, and every added row is marked 'interpolated': True so that
    it is never mistaken for a detection. With `avoid_covered` a row is not added where a row of another track of the same
    frame already stands within `cover` box heights (that person is shown by the other track, a second dot would be a double).
    Returns (new tracks, number of rows added).
    """
    added = 0
    result = {}
    by_frame = {}
    if avoid_covered:
        for tid, rows in tracks.items():
            for row in rows:
                by_frame.setdefault(row['frame'], []).append((tid, _centre(row['box'])))
    for tid, rows in tracks.items():
        rows = sorted(rows, key=lambda r: r['frame'])
        filled = []
        for index, row in enumerate(rows):
            filled.append(row)
            if index + 1 >= len(rows):
                continue
            following = rows[index + 1]
            gap = following['frame'] - row['frame'] - 1
            if 1 <= gap <= max_gap:
                for k in range(1, gap + 1):
                    share = k / (gap + 1)
                    box = [round(a + (b - a) * share, 1) for a, b in zip(row['box'], following['box'])]
                    if avoid_covered:
                        cx, cy = _centre(box)
                        if any(other != tid and math.hypot(cx - ox, cy - oy) < cover * _height(box) for other, (ox, oy) in by_frame.get(row['frame'] + k, [])):
                            continue
                    filled.append({'frame': row['frame'] + k, 'team': row['team'], 'box': box, 'interpolated': True})
                    added += 1
        result[tid] = filled
    return result, added


def _overlap_share(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    return width * height / max(1e-6, min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])))


def drop_duplicates(tracks, max_distance=0.35, min_share=0.5, *, different_pairs=()):
    """Remove the rows of a track in the frames where another track already shows the same person.

    Two rows of one frame are the same person when their box centres lie closer than `max_distance` body heights and the
    boxes overlap by at least `min_share` of the smaller one. The longer track keeps the row; on a tie the lower id keeps it.
    Returns (new tracks, number of rows dropped). Tracks that lose every row disappear.
    """
    forbidden = {frozenset(map(str, pair)) for pair in different_pairs}
    lengths = {tid: len(rows) for tid, rows in tracks.items()}
    by_frame = {}
    for tid, rows in tracks.items():
        for row in rows:
            by_frame.setdefault(row['frame'], []).append((tid, row))
    dropped = set()
    for frame, items in by_frame.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (t1, r1), (t2, r2) = items[i], items[j]
                if frozenset((str(t1),str(t2))) in forbidden:
                    continue
                if (t1, frame) in dropped or (t2, frame) in dropped:
                    continue
                b1, b2 = r1['box'], r2['box']
                height = max(b1[3] - b1[1], b2[3] - b2[1], 1.0)
                distance = math.hypot((b1[0] + b1[2]) / 2 - (b2[0] + b2[2]) / 2, (b1[1] + b1[3]) / 2 - (b2[1] + b2[3]) / 2)
                if distance < max_distance * height and _overlap_share(b1, b2) >= min_share:
                    loser = t2 if (lengths[t1], -_order(t1)) >= (lengths[t2], -_order(t2)) else t1
                    dropped.add((loser, frame))
    result = {}
    for tid, rows in tracks.items():
        kept = [row for row in rows if (tid, row['frame']) not in dropped]
        if kept:
            result[tid] = kept
    return result, len(dropped)


def _order(tid):
    try:
        return int(tid)
    except (TypeError, ValueError):
        return 0
