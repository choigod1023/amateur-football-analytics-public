"""Find the moments of a whole half that are worth coaching, from player positions in metres.

Moments: a run in behind of the focus team (good), a run in behind of the other team that the focus team allowed (poor), a most advanced
player left alone for a long time (poor), the own back line dropping deep (poor) and confirmed goals (good, with the attack that led to it).
Every moment carries the time it happened and the time its sequence ends: when a confirmed goal follows within 45 s the sequence runs on
to the goal, otherwise it is followed for 14 s. There is no ball in this data, so a shot that is not a goal is never reported.
"""
from app.tactical_concepts import runs_in_behind

FOLLOW_SECONDS = 14.0
GOAL_WINDOW = 45.0
MIN_GAP = 35.0
TITLES = {'box_attack': '박스 침투 공격', 'run': '침투', 'conceded_run': '상대 침투 허용', 'isolated': '고립된 공격수', 'line_drop': '수비 라인 하락', 'goal': '득점'}
POLARITY = {'box_attack': 'good', 'run': 'good', 'conceded_run': 'poor', 'isolated': 'poor', 'line_drop': 'poor', 'goal': 'goal'}


def smooth(values, radius=3):
    """Median of +-`radius` seconds around every second: the measured back line jumps by several metres from one second to the next."""
    ordered = sorted(values)
    out = {}
    for second in ordered:
        near = sorted(values[t] for t in range(second - radius, second + radius + 1) if t in values)
        out[second] = near[len(near) // 2]
    return out


def _isolated_spells(series, minimum_seconds=6, isolation=12.0):
    """Stretches of seconds in which the team stands in the opponent half and its most advanced player is more than `isolation` metres from every teammate."""
    spells, current = [], []
    for second in sorted(series):
        m = series[second]
        if m['centre'] > 0 and m['leader_isolation'] > isolation and (not current or second - current[-1] <= 2):
            current.append(second)
        else:
            if len(current) >= minimum_seconds:
                spells.append(current)
            current = [second] if (m['centre'] > 0 and m['leader_isolation'] > isolation) else []
    if len(current) >= minimum_seconds:
        spells.append(current)
    return spells


def _line_drops(back_line_other, change=10.0, within=10):
    """Moments when the own back line (seen by the other team as `back_line_other`, metres toward the goal it attacks) moves at least `change`
    metres toward the own goal within `within` seconds. Returns [(second, metres)]."""
    found, last = [], -10 ** 9
    for second in sorted(back_line_other):
        for later in range(second + 1, second + within + 1):
            if later in back_line_other and back_line_other[later] - back_line_other[second] >= change and second - last > within:
                found.append((later, back_line_other[later] - back_line_other[second]))
                last = later
                break
    return found


def _box_attacks(paths_team, pitch_length, fps, minimum=3, seconds=2):
    """Stretches in which at least `minimum` players of the team stand in the penalty area of the goal it attacks for `seconds` seconds. On the confirmed
    goals of one match this picked out the attack within a few seconds for most of them, which a run in behind never did.
    Returns [(first second, most players in the box)]."""
    counts = {}
    for path in paths_team.values():
        for frame, u, y in path:
            if u >= pitch_length / 2 - 16.5 and abs(y) <= 20.16:
                counts[frame] = counts.get(frame, 0) + 1
    per_second = {}
    for frame, n in counts.items():
        second = int(frame // fps)
        per_second[second] = max(per_second.get(second, 0), n)
    found, current = [], []
    for second in sorted(per_second):
        if per_second[second] >= minimum and (not current or second - current[-1] <= 1):
            current.append(second)
        else:
            if len(current) >= seconds:
                found.append((current[0], max(per_second[s] for s in current)))
            current = [second] if per_second[second] >= minimum else []
    if len(current) >= seconds:
        found.append((current[0], max(per_second[s] for s in current)))
    return found


def mine_events(paths_team, paths_other, series_team, series_other, goals_seconds, fps=5.0, offset=0.0, max_events=8, max_poor=3, pitch_length=89.0):
    """Events of a half as dicts: kind, polarity, title, time (video seconds), end (video seconds when the sequence ends), strength, track, team ('team' or 'other'),
    goal_follow. paths_*: {track: [(frame, u, y)]} with u toward the goal that team attacks; series_*: {second: second_metrics of that team};
    goals_seconds: video seconds of confirmed goals scored by the focus team."""
    back_team = {s: m['opponent_back_line'] for s, m in series_team.items()}
    back_other = {s: m['opponent_back_line'] for s, m in series_other.items()}
    smooth_other = smooth(back_other)
    raw = []
    for run in runs_in_behind(paths_team, back_team, fps):
        raw.append({'kind': 'run', 'time': offset + run['end'], 'strength': min(1.0, run['speed'] / 9.0), 'track': run['track'], 'team': 'team', 'speed_kmh': round(run['speed'] * 3.6)})
    for run in runs_in_behind(paths_other, back_other, fps):
        raw.append({'kind': 'conceded_run', 'time': offset + run['end'], 'strength': min(1.0, run['speed'] / 9.0) + 0.15, 'track': run['track'], 'team': 'other', 'speed_kmh': round(run['speed'] * 3.6)})
    for second, players in _box_attacks(paths_team, pitch_length, fps):
        raw.append({'kind': 'box_attack', 'time': offset + second, 'strength': min(1.0, 0.45 + 0.12 * players), 'track': series_team.get(second, {}).get('leader'), 'team': 'team', 'players': players})
    for spell in _isolated_spells(series_team):
        middle = spell[len(spell) // 2]
        raw.append({'kind': 'isolated', 'time': offset + middle, 'strength': min(1.0, len(spell) / 24.0), 'track': series_team[middle]['leader'], 'team': 'team'})
    for second, metres in _line_drops(smooth_other):
        raw.append({'kind': 'line_drop', 'time': offset + second, 'strength': min(0.6, metres / 30.0), 'track': None, 'team': 'team'})
    goals = sorted(goals_seconds)
    chosen = []
    for goal in goals:
        # the strongest good moment that leads into the goal carries the goal; without one the goal is a moment of its own
        leading = [e for e in raw if POLARITY[e['kind']] == 'good' and goal - GOAL_WINDOW <= e['time'] <= goal - 3.0 + (13.0 if e['kind'] == 'box_attack' else 0.0)]
        if leading:
            best = max(leading, key=lambda e: e['strength'])
            raw.remove(best)
            chosen.append({**best, 'goal_at': goal, 'strength': best['strength'] + 2.0})
        else:
            second = int(goal - offset)
            chosen.append({'kind': 'goal', 'time': goal - 8.0, 'strength': 2.0, 'track': series_team.get(second - 1, {}).get('leader'), 'team': 'team', 'goal_at': goal})
    # the other moments are taken in turns by kind (best of every kind first) so that one kind of moment cannot fill the half
    queues = {kind: sorted([e for e in raw if e['kind'] == kind], key=lambda e: -e['strength']) for kind in ('box_attack', 'run', 'conceded_run', 'isolated', 'line_drop')}
    limit = {'box_attack': 3, 'run': 3, 'conceded_run': 2, 'isolated': 2, 'line_drop': 1}
    taken = {kind: 0 for kind in queues}
    poor = 0
    progressed = True
    while len(chosen) < max_events and progressed:
        progressed = False
        for kind in queues:
            if len(chosen) >= max_events or taken[kind] >= limit[kind]:
                continue
            while queues[kind]:
                event = queues[kind].pop(0)
                if any(abs(event['time'] - other['time']) < MIN_GAP for other in chosen) or any(abs(event['time'] - g) < 12 for g in goals):
                    continue
                if POLARITY[kind] == 'poor' and poor >= max_poor:
                    break
                poor += POLARITY[kind] == 'poor'
                taken[kind] += 1
                chosen.append(event)
                progressed = True
                break
    result = []
    for event in sorted(chosen, key=lambda e: e['time']):
        goal = event.get('goal_at') or next((g for g in goals if event['time'] - (10.0 if event['kind'] == 'box_attack' else 0.0) < g <= event['time'] + GOAL_WINDOW), None)
        end = goal + 3.0 if goal else event['time'] + FOLLOW_SECONDS
        result.append({**event, 'polarity': POLARITY[event['kind']], 'title': TITLES[event['kind']], 'end': end, 'goal_follow': goal is not None, 'goal_at': goal})
    return result
