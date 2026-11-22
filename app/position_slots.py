"""Position slots from where the players of a team stand: goalkeeper, then the defending, midfield and forward lines, each from the left hand to the right hand of the team.

This names a place in the team's shape ('left back', 'right central midfielder'), not a person. The team is cut into three lines at the two largest gaps in depth (as app.tactical_feedback.team_lines does) and the players of a
line are put in order from left to right as the team sees it: the team attacks toward +u, the camera looks at the pitch from the side of positive y, so for a team attacking toward +x its right hand is +y and for a team
attacking toward -x its right hand is -y (`lateral = y * direction`). With fewer than 8 players found the lines are not reliable and the result is only 'defence / midfield / attack'.
"""
from app.goalkeeper import goalkeeper_depth_is_keeper

SLOT_NAMES = {
    'defence': {1: ['CB'], 2: ['LCB', 'RCB'], 3: ['LCB', 'CB', 'RCB'], 4: ['LB', 'LCB', 'RCB', 'RB'], 5: ['LWB', 'LCB', 'CB', 'RCB', 'RWB']},
    'midfield': {1: ['CM'], 2: ['LCM', 'RCM'], 3: ['LCM', 'CM', 'RCM'], 4: ['LM', 'LCM', 'RCM', 'RM'], 5: ['LM', 'LCM', 'CM', 'RCM', 'RM']},
    'attack': {1: ['ST'], 2: ['LS', 'RS'], 3: ['LW', 'ST', 'RW'], 4: ['LW', 'LS', 'RS', 'RW']},
}
POSITIONS = ('DF', 'MF', 'FW', 'GK', 'LB', 'LCB', 'CB', 'RCB', 'RB', 'LWB', 'RWB', 'LM', 'LCM', 'CM', 'RCM', 'RM', 'LW', 'RW', 'LS', 'ST', 'RS')
POSITION_TEXT = {'GK': '골키퍼', 'LB': '왼쪽 풀백', 'LCB': '왼쪽 센터백', 'CB': '센터백', 'RCB': '오른쪽 센터백', 'RB': '오른쪽 풀백', 'LWB': '왼쪽 윙백', 'RWB': '오른쪽 윙백', 'LM': '왼쪽 미드필더',
                 'LCM': '왼쪽 중앙 미드필더', 'CM': '중앙 미드필더', 'RCM': '오른쪽 중앙 미드필더', 'RM': '오른쪽 미드필더', 'LW': '왼쪽 윙', 'RW': '오른쪽 윙', 'LS': '왼쪽 공격수', 'ST': '공격수',
                 'RS': '오른쪽 공격수', 'defence': '수비', 'midfield': '중원', 'attack': '공격', 'DF': '수비수', 'MF': '미드필더', 'FW': '공격수(FW)'}
GOALKEEPER_GAP = 8.0         # metres the deepest player must stand behind the next one to be called the goalkeeper


def _lines(depths):
    """Indexes of the three lines of players sorted by depth (cut at the two largest gaps)."""
    order = sorted(range(len(depths)), key=lambda i: depths[i])
    gaps = sorted(range(1, len(order)), key=lambda k: depths[order[k]] - depths[order[k - 1]], reverse=True)[:2]
    cut_a, cut_b = sorted(gaps)
    return [order[:cut_a], order[cut_a:cut_b], order[cut_b:]]


def assign_slots(players, direction=1):
    """players: [(track id, x, y)] of one team in metres at one moment (x along the pitch, y across it, positive y toward the camera), direction: +1 when the team attacks toward +x.

    Returns {'slots': {track id: slot}, 'formation': '4-4-2' or None, 'goalkeeper': track id or None}. The slot is a code of POSITIONS, or 'defence' / 'midfield' / 'attack' when fewer than 8 players are found."""
    if len(players) < 4:
        return {'slots': {}, 'formation': None, 'goalkeeper': None}
    rows = sorted(((t, x * direction, y * direction) for t, x, y in players), key=lambda r: r[1])           # (track, depth, lateral) from the own goal forward
    slots, goalkeeper = {}, None
    if goalkeeper_depth_is_keeper([r[1] for r in rows]):
        goalkeeper = rows[0][0]
        slots[goalkeeper] = 'GK'
        rows = rows[1:]
    if len(rows) < 6:
        thirds = ['defence'] * (len(rows) - len(rows) // 3 * 2) + ['midfield'] * (len(rows) // 3) + ['attack'] * (len(rows) // 3)
        for (t, _d, _l), name in zip(rows, thirds):
            slots[t] = name
        return {'slots': slots, 'formation': None, 'goalkeeper': goalkeeper}
    if len(rows) < 8:
        coarse = _lines([r[1] for r in rows])
        for line, name in zip(coarse, ('defence', 'midfield', 'attack')):
            for i in line:
                slots[rows[i][0]] = name
        return {'slots': slots, 'formation': None, 'goalkeeper': goalkeeper}
    lines = _lines([r[1] for r in rows])
    if not (2 <= len(lines[0]) <= 5 and 1 <= len(lines[1]) <= 5 and 1 <= len(lines[2]) <= 4):          # a shape like 9-1-1 is the cut of a noisy picture, not a formation
        for line, name in zip(lines, ('defence', 'midfield', 'attack')):
            for i in line:
                slots[rows[i][0]] = name
        return {'slots': slots, 'formation': None, 'goalkeeper': goalkeeper}
    sizes = []
    for line, name in zip(lines, ('defence', 'midfield', 'attack')):
        ordered = sorted(line, key=lambda i: rows[i][2])               # from the left hand to the right hand of the team
        names = SLOT_NAMES[name].get(len(ordered)) or [f'{name}{k + 1}' for k in range(len(ordered))]
        for i, slot in zip(ordered, names):
            slots[rows[i][0]] = slot
        sizes.append(len(ordered))
    return {'slots': slots, 'formation': '-'.join(str(n) for n in sizes), 'goalkeeper': goalkeeper}
