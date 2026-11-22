"""Tactical observations from player positions in metres: estimated places for missed players, open passing lanes,
lines of a team, breakthrough runs and plain-language feedback.

Positions are (x, y) in metres on the pitch (x along the length, y across). A team attacks toward +x when its
`direction` is +1 and toward -x when it is -1. Everything here is derived from tracked positions only: there is no ball,
so nothing says who has the ball, who passed to whom or how well a player dribbles. Estimated players are guesses
(marked with a kind) and the feedback always says how many players of a team were really seen.
"""
from app.team_style import short_name
import math

from app.goalkeeper import without_goalkeeper

TEAM_SIZE = 11
LANE_MIN, LANE_MAX, LANE_CLEARANCE = 6.0, 35.0, 2.5
SPRINT_SPEED = 5.5


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def segment_distance(point, start, end):
    """Shortest distance from a point to the segment start-end."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return _distance(point, start)
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2))
    return _distance(point, (start[0] + t * dx, start[1] + t * dy))


def estimate_missing(present, recent, pitch, team_size=TEAM_SIZE, drift=(0.0, 0.0), near=3.0, fill_holes=False):
    """Places for the players of a team that are not seen in this frame.

    present: [(x, y)] seen now. recent: [(x, y, seconds since last seen)] of players seen shortly before (most recent
    first). Each recent player is carried along with the movement of the team (`drift`, the move of the team centre since)
    and kept unless a seen teammate already stands within `near` metres (that is probably the same person under a new
    track). Measured on the second half of this match, a player lost for up to 5 s is carried forward to within 10 m in 91 %
    of the cases (median 4 m), after 10 s in 77 % (median 6 m). Players that were never seen are NOT placed unless
    `fill_holes` is set: putting them into the largest hole of the team missed by 30 m or more (median), worse than the team
    centre (14 m), so a guess like that would only look plausible. With fill_holes the remaining players go to the holes.
    Returns [{'x', 'y', 'kind': 'recent' | 'gap'}]; nothing is returned when no player is seen at all."""
    missing = team_size - len(present)
    if missing <= 0 or not present:
        return []
    half_length, half_width = pitch['length'] / 2, pitch['width'] / 2
    points, estimated = list(present), []
    for x, y, _age in recent:
        if len(estimated) >= missing:
            break
        x, y = x + drift[0], y + drift[1]
        if abs(x) > half_length or abs(y) > half_width or any(_distance((x, y), p) < near for p in points):
            continue
        estimated.append({'x': x, 'y': y, 'kind': 'recent'})
        points.append((x, y))
    if not fill_holes:
        return estimated
    xs, ys = [p[0] for p in present], [p[1] for p in present]
    low_x, high_x, low_y, high_y = max(-half_length, min(xs) - 5), min(half_length, max(xs) + 5), max(-half_width, min(ys) - 5), min(half_width, max(ys) + 5)
    while len(estimated) < missing:
        best, best_distance = None, -1.0
        steps = 24
        for i in range(steps + 1):
            for j in range(steps + 1):
                candidate = (low_x + (high_x - low_x) * i / steps, low_y + (high_y - low_y) * j / steps)
                nearest = min(_distance(candidate, p) for p in points)
                if nearest > best_distance:
                    best, best_distance = candidate, nearest
        estimated.append({'x': best[0], 'y': best[1], 'kind': 'gap'})
        points.append(best)
    return estimated


def open_lanes(team, opponents, direction=1, minimum=LANE_MIN, maximum=LANE_MAX, clearance=LANE_CLEARANCE):
    """Passing lanes between teammates that no opponent stands close to.

    team / opponents: [(x, y)]. A lane runs from player i to player j (length between `minimum` and `maximum` metres) and
    is open when every opponent is farther than `clearance` metres from the line. Returns [{'from', 'to', 'length',
    'forward' (the receiver is at least 3 m nearer the opponent goal), 'clearance'}]."""
    lanes = []
    for i, a in enumerate(team):
        for j, b in enumerate(team):
            if i == j:
                continue
            length = _distance(a, b)
            if not minimum <= length <= maximum:
                continue
            gap = min((segment_distance(o, a, b) for o in opponents), default=99.0)
            if gap >= clearance:
                lanes.append({'from': i, 'to': j, 'length': round(length, 1), 'forward': (b[0] - a[0]) * direction >= 3.0, 'clearance': round(gap, 1)})
    return lanes


def team_lines(points, direction=1):
    """Depth (metres toward the opponent goal) of the defensive, middle and forward line of a team and the gaps between them.

    The goalkeeper is left out by app/goalkeeper.py: the deepest player when he stands close to the own goal line and behind the rest. Players
    sorted by depth are cut into three groups at the two largest gaps. Returns None for fewer than 6 players."""
    depths, _ = without_goalkeeper([p[0] * direction for p in points], key=lambda d: d)
    if len(depths) < 6:
        return None
    gaps = sorted(range(1, len(depths)), key=lambda k: depths[k] - depths[k - 1], reverse=True)[:2]
    cut_a, cut_b = sorted(gaps)
    groups = [depths[:cut_a], depths[cut_a:cut_b], depths[cut_b:]]
    centres = [sum(g) / len(g) for g in groups]
    return {'defence': round(centres[0], 1), 'midfield': round(centres[1], 1), 'attack': round(centres[2], 1), 'sizes': [len(g) for g in groups],
            'defence_to_midfield': round(centres[1] - centres[0], 1), 'midfield_to_attack': round(centres[2] - centres[1], 1)}


def speeds(path, fps=5.0, window=5, limit=9.0):
    """Speeds (m/s) along a path [(frame, x, y)] measured over `window` frames and capped at `limit` against measurement noise."""
    out = []
    for k in range(len(path)):
        j = max(0, k - window)
        dt = (path[k][0] - path[j][0]) / fps
        out.append(min(limit, _distance(path[k][1:], path[j][1:]) / dt) if dt > 0 else 0.0)
    return out


def breakthrough_runs(path, opponents_at, direction=1, fps=5.0, reach=6.0, speed_floor=SPRINT_SPEED):
    """Moments when a player runs fast toward the opponent goal and gets past an opponent who stood ahead within `reach` metres.

    path: [(frame, x, y)]; opponents_at(frame) -> [(x, y)]. Without the ball this only shows a running move that beat a
    defender, not a dribble. Returns [{'frame', 'speed', 'beaten'}] with runs at least 2 s apart."""
    found, v = [], speeds(path, fps)
    last = -10 ** 9
    for k in range(1, len(path)):
        frame, x, y = path[k]
        if v[k] < speed_floor or frame - last < 2 * fps or (x - path[k - 1][1]) * direction <= 0:
            continue
        before = opponents_at(path[max(0, k - int(fps))][0])
        start = path[max(0, k - int(fps))]
        ahead = [o for o in before if 0 < (o[0] - start[1]) * direction <= reach and abs(o[1] - start[2]) <= reach / 2]
        now = opponents_at(frame)
        beaten = sum(1 for o in ahead if any(_distance(o, n) < 2.5 and (x - n[0]) * direction > 0 for n in now))
        if beaten:
            found.append({'frame': frame, 'speed': round(v[k], 1), 'beaten': beaten})
            last = frame
    return found


def feedback(team_name, seen, estimated, lines, lanes, baseline=None):
    """Plain-language observations (Korean) for one team over a stretch, from numbers of the same stretch.

    seen: average number of players really seen; estimated: average number of estimated players; lines: team_lines result;
    lanes: {'open': average open lanes, 'forward_open': average open forward lanes, 'possible': average possible lanes};
    baseline: the same two dicts for a longer stretch of the same team ({'lines': ..., 'lanes': ...}); when given, lanes and line
    gaps are judged against it (a window is notable only when it differs from the usual of the team), otherwise against fixed limits."""
    unknown = max(0.0, TEAM_SIZE - seen - estimated)
    notes = [f'{short_name(team_name)}: 실제로 확인된 선수는 평균 {seen:.1f}명이고, 최근에 보였다가 사라져서 예상 위치로 표시한 선수가 {estimated:.1f}명이며, 위치를 알 수 없는 선수가 {unknown:.1f}명입니다.']
    usual = (baseline or {}).get('lines')
    if lines:
        wide = usual['defence_to_midfield'] * 1.3 if usual else 22
        if lines['defence_to_midfield'] > wide:
            notes.append(f'수비 라인과 미드필드 라인의 간격이 {lines["defence_to_midfield"]:.0f}m로 {"평소보다 " if usual else ""}넓습니다. 상대가 두 라인 사이로 받으면 수비가 뒤에서 대응하게 됩니다.')
        elif usual and lines['defence_to_midfield'] < usual['defence_to_midfield'] * 0.7:
            notes.append(f'수비 라인과 미드필드 라인의 간격이 {lines["defence_to_midfield"]:.0f}m로 평소보다 좁아졌습니다. 촘촘해진 대신 수비 뒤 공간이 열릴 수 있습니다.')
        isolated = usual['midfield_to_attack'] * 1.3 if usual else 28
        if lines['midfield_to_attack'] > isolated:
            notes.append(f'미드필드 라인과 공격 라인이 {lines["midfield_to_attack"]:.0f}m 떨어져 {"평소보다 " if usual else ""}공격수가 고립되기 쉽습니다.')
    base = (baseline or {}).get('lanes')
    if lanes and lanes.get('possible'):
        share, forward = lanes['open'] / lanes['possible'], lanes['forward_open']
        base_share = base['open'] / base['possible'] if base and base.get('possible') else 0.45
        base_forward = base['forward_open'] if base else 6.0
        if share < base_share * 0.75:
            notes.append(f'동료 사이 패스길 중 열린 것이 {share * 100:.0f}%로 {"평소(" + format(base_share * 100, ".0f") + "%)보다 " if base else ""}적습니다. 상대가 패스 라인을 막고 있거나 선수들이 서로 겹쳐 서 있다는 뜻입니다.')
        if forward < base_forward * 0.6:
            notes.append(f'앞쪽으로 향하는 열린 패스길이 평균 {forward:.1f}개로 {"평소(" + format(base_forward, ".1f") + "개)보다 " if base else ""}적습니다. 폭을 넓히거나 한 명이 라인 사이로 내려와 받는 움직임이 필요합니다.')
        elif forward > base_forward * 1.4:
            notes.append(f'앞쪽으로 향하는 열린 패스길이 평균 {forward:.1f}개로 {"평소(" + format(base_forward, ".1f") + "개)보다 " if base else ""}많아, 전진 패스로 수비 뒤를 노릴 수 있는 시간대입니다.')
    return [n for n in notes if n]
