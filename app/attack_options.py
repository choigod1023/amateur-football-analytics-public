"""What an attack looked like and which passing lanes the attacking team had at a moment, read from player positions in metres.

For a moment (a goal, or an attack that did not end in a goal) this answers football questions a coach asks:
  where the play was       the side of the pitch of the player with the ball and how far the team's centre moved sideways in the seconds before (a switch of play)
  how wide the team stood  across the pitch among the players in the opponent half
  the passing lanes        from the player with the ball to every teammate within MAX_PASS metres. A lane is open when no opponent stands within LANE_CLEAR metres of the
                           line of the pass (a defender that close can step in and cut it) and blocked otherwise, with the blocking defender named. A lane that goes
                           to the other side of the pitch from the carrier is a switch-of-play lane.
  how crowded the goal side was   opponents ahead of the carrier.

There is no ball in this data. The player with the ball is given by the caller (when the ball finder saw the ball next to a player) or taken to be the most
advanced player of the team, and the result says which (`carrier_source`). Players the tracker did not find are not in the numbers, so 'open' means open among the
players that were found; the video draws the same players so that a coach can check it. `allowed` limits the attacking team to the track ids whose shirt
colour fits the team (the tracker sometimes labels a player of the other team).
"""
import math

LANE_CLEAR = 3.0
MAX_PASS = 35.0
WEAK_SIDE_METRES = 15.0         # a lane that ends this far across the pitch from the carrier is a switch of play


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def segment_distance(point, a, b):
    """Distance of a point to the segment a-b (all (u, y) in metres)."""
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return _distance(point, a)
    t = max(0.0, min(1.0, ((point[0] - ax) * dx + (point[1] - ay) * dy) / length2))
    return _distance(point, (ax + t * dx, ay + t * dy))


def side_of(y):
    return 'near' if y > 12 else 'far' if y < -12 else 'centre'


def _frame_players(by_frame, team, other, direction, frame, radius=1):
    """The (track, u, y) lists of both teams at the frame near `frame` that shows the most players (u: metres toward the goal the team attacks, for both lists)."""
    best, best_count = None, -1
    for f in range(frame - radius, frame + radius + 1):
        teams = by_frame.get(f)
        if not teams:
            continue
        count = len(teams.get(team, [])) + len(teams.get(other, []))
        if count > best_count:
            best, best_count = (f, teams), count
    if best is None:
        return None
    f, teams = best
    return f, [(t, x * direction, y) for t, x, y in teams.get(team, [])], [(t, x * direction, y) for t, x, y in teams.get(other, [])]


def analyse(by_frame, team, other, direction, fps, offset, time, carrier=None, allowed=None, look_back=8.0):
    """The facts of the attack at `time` (video seconds). Returns None when fewer than four players of each team were found there.

    {'frame', 'carrier' (track id), 'carrier_source' ('given' or 'most advanced'), 'play_y', 'side', 'lanes' [{'track', 'u', 'y', 'length', 'clear', 'open', 'blocker',
     'forward', 'across'}], 'shift' (metres the centre of the team moved sideways in `look_back` seconds), 'width', 'goal_side' (opponents ahead of the carrier), 'ours', 'theirs'}"""
    frame = int(round((time - offset) * fps))
    now = _frame_players(by_frame, team, other, direction, frame, radius=1)
    if now is None:
        return None
    frame, ours, theirs = now
    pool = [p for p in ours if allowed is None or p[0] in allowed]
    if len(pool) < 4 or len(theirs) < 4:
        return None
    outfield = [p for p in pool if p[1] > -35]
    if not outfield:
        return None
    given = carrier is not None and any(p[0] == carrier for p in pool)
    lead = next(p for p in pool if p[0] == carrier) if given else max(outfield, key=lambda p: p[1])
    lanes = []
    for tid, u, y in pool:
        if tid == lead[0]:
            continue
        length = _distance((u, y), (lead[1], lead[2]))
        if length > MAX_PASS or length < 4.0:
            continue
        near = min(((segment_distance((ou, oy), (lead[1], lead[2]), (u, y)), t) for t, ou, oy in theirs), key=lambda d: d[0])
        lanes.append({'track': tid, 'u': round(u, 1), 'y': round(y, 1), 'length': round(length, 1), 'clear': round(float(near[0]), 1), 'open': bool(near[0] >= LANE_CLEAR),
                      'blocker': None if near[0] >= LANE_CLEAR else near[1], 'forward': bool(u >= lead[1] - 3.0), 'across': bool(abs(y - lead[2]) >= WEAK_SIDE_METRES)})
    earlier = _frame_players(by_frame, team, other, direction, int(round((time - look_back - offset) * fps)))
    shift = 0.0
    if earlier and len(earlier[1]) >= 4:
        shift = sum(y for _t, _u, y in pool) / len(pool) - sum(y for _t, _u, y in earlier[1]) / len(earlier[1])
    forward = [p for p in pool if p[1] > 0]
    width = max(y for _t, _u, y in forward) - min(y for _t, _u, y in forward) if len(forward) >= 2 else 0.0
    goal_side = sum(1 for _t, ou, _y in theirs if ou > lead[1] - 2)
    return {'frame': frame, 'carrier': lead[0], 'carrier_source': 'given' if given else 'most advanced', 'play_y': round(lead[2], 1), 'carrier_u': round(lead[1], 1), 'side': side_of(lead[2]),
            'lanes': sorted(lanes, key=lambda l: (not l['open'], -l['length'])), 'shift': round(shift, 1), 'width': round(width, 1), 'goal_side': goal_side,
            'ours': len(pool), 'theirs': len(theirs)}


LANE_NAMES = {'wing': '측면', 'half_space': '측면과 중앙 사이(하프스페이스)', 'centre': '중앙'}
THIRD_NAMES = {'own': '우리 진영', 'middle': '중원', 'final': '상대 진영 앞쪽'}


def zone_name(u, y, pitch_length, pitch_width):
    """'가까운 쪽 측면의 중원' style name of a place (u metres toward the goal attacked, y across the pitch; positive y is the side of the picture nearest the camera)."""
    edge = abs(y) / (pitch_width / 2)
    lane = 'wing' if edge >= 0.62 else 'half_space' if edge >= 0.26 else 'centre'
    third = 'own' if u < -pitch_length / 6 else 'final' if u > pitch_length / 6 else 'middle'
    side = '' if lane == 'centre' else ('가까운 쪽 ' if y > 0 else '먼 쪽 ')
    return f'{side}{LANE_NAMES[lane]}의 {THIRD_NAMES[third]}'


def _count_words(n):
    return {0: '한 명도', 1: '한 명', 2: '두 명', 3: '세 명', 4: '네 명', 5: '다섯 명'}.get(n, f'{n}명')


def describe(by_frame, team, other, direction, fps, offset, time, facts, pitch_length=89.0, pitch_width=62.0, allowed=None, steps=(-8.0, -4.0, 0.0)):
    """The scene and the space of an attack in words, from player positions. Returns {'path': 'where it started and went', 'scene': [lines], 'space': [lines]}.

    scene   where the most advanced player of the team was 8 s, 4 s and 0 s before `time` (zone and third of the pitch), how the opponent defended (how many defenders
            stood in its back group, how wide, how many of ours were in that area) and a switch of play
    space   the room behind the opponent back line up to the goal line, the five lanes of the last 35 m (far wing, far half-space, centre, near half-space, near wing)
            with how many opponents and how many of ours stood in each, and which lane was empty of opponents (the space to attack) or most crowded."""
    marks = []
    for dt in steps:
        now = _frame_players(by_frame, team, other, direction, int(round((time + dt - offset) * fps)), radius=1)
        if not now:
            continue
        _f, ours, theirs = now
        pool = [p for p in ours if (allowed is None or p[0] in allowed) and p[1] > -35]
        if pool:
            lead = max(pool, key=lambda p: p[1])
            marks.append((dt, lead, ours, theirs))
    if len(marks) < 2:
        return None
    names = [zone_name(m[1][1], m[1][2], pitch_length, pitch_width) for m in marks]
    unique = [names[0]] + [n for a, n in zip(names, names[1:]) if n != a]
    path = ' → '.join(unique) if len(unique) > 1 else unique[0] + '에서 머물렀습니다'
    _dt, lead, ours, theirs = marks[-1]
    pool = [p for p in ours if allowed is None or p[0] in allowed]
    scene = [f'가장 앞선 선수의 위치가 {path} 순서로 옮겨 갔습니다' if len(unique) > 1 else f'가장 앞선 선수는 {unique[0]}에 머물렀습니다']
    deepest = sorted(theirs, key=lambda p: -p[1])
    back = [p for p in deepest if p[1] < pitch_length / 2 - 2.0][:4]       # the goalkeeper stands on the goal line and is left out
    space = []
    if len(back) >= 3:
        line = sum(p[1] for p in back) / len(back)
        width = max(p[2] for p in back) - min(p[2] for p in back)
        mine_there = sum(1 for p in pool if p[1] >= line - 8.0)
        scene.append(f'상대 수비 {len(back)}명이 박스 앞에서 폭 {int(width)}미터로 서 있었고, 같은 구역에 우리 선수는 {_count_words(mine_there)} 있었습니다'
                     + (' (수적 열세)' if mine_there < len(back) else ' (수적 우위)' if mine_there > len(back) else ' (동수)'))
        gap = pitch_length / 2 - line
        space.append(f'상대 수비 라인 뒤에서 골라인까지 약 {int(gap)}미터' + (' 비어 있어 뒤로 넘기는 패스가 가능했습니다' if gap >= 12 else '라 뒤 공간이 좁았습니다'))
    if abs(facts.get('shift', 0.0)) >= 12:
        scene.append(f'공격하는 동안 팀의 무게중심이 옆으로 약 {int(abs(facts["shift"]))}미터 움직여 공격 방향이 바뀌었습니다')
    zones = [('먼 쪽 측면', lambda y: y <= -pitch_width * 0.31), ('먼 쪽 하프스페이스', lambda y: -pitch_width * 0.31 < y <= -pitch_width * 0.13), ('중앙', lambda y: abs(y) < pitch_width * 0.13),
             ('가까운 쪽 하프스페이스', lambda y: pitch_width * 0.13 <= y < pitch_width * 0.31), ('가까운 쪽 측면', lambda y: y >= pitch_width * 0.31)]
    table = []
    for name, inside in zones:
        t = sum(1 for _t, u, y in theirs if u >= pitch_length / 2 - 35 and u < pitch_length / 2 - 1 and inside(y))
        o = sum(1 for _t, u, y in pool if u >= pitch_length / 2 - 35 and inside(y))
        table.append((name, t, o))
    empty = [z for z in table if z[1] == 0]
    crowded = max(table, key=lambda z: z[1])
    if crowded[1] >= 2:
        space.append(f'{crowded[0]}에 상대 수비수가 {_count_words(crowded[1])} 몰려 있었습니다(우리 선수 {_count_words(crowded[2])})')
    if empty:
        far = max(empty, key=lambda z: (z[2] == 0, abs(0 if z[0] == '중앙' else 1)))
        space.append(f'{far[0]} 구역에는 상대 수비수가 없었고 우리 선수는 {_count_words(far[2])} 있었습니다' + (': 비어 있는 공간이었습니다' if far[2] == 0 else ''))
    return {'path': path, 'scene': scene[:3], 'space': space[:3]}
