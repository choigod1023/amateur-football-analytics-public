"""How the other team played in a half, from the positions only, for the half-time report: their back line when they defended, where they stood when they defended and when they
attacked, the side they came in on, how many players they sent forward or left up front, and how wide and long they stood.

The live accumulator (app/halftime_accumulator.py) calls add_second() once per second; the report (app/halftime_report.py) calls summary() on the minute buckets. Everything is in our
team's frame: u towards the goal we attack, v across with our left negative (facing the way we attack), the same frame as the existing entries ("상대가 들어온 곳").

The other team is seen badly (4 to 8 of them per second, the far side and their keeper are missed, a wrong colour read mixes the teams), so every item carries the amount of evidence and is
not judged when there is too little. The limits are fixed in work/overnight-1124/halftime-opp/rules.md (saved before any match was run) and come from the pitch size or from that file:
  * a second counts when 7 to 11 of their players are seen (7 = app.team_tactics.MIN_PLAYERS; 12 or more is a colour mix-up); the counts of players need 8 to 11;
  * phase: the mean u of all players seen (both teams) > 0 -> they defend, < 0 -> they attack (there is no ball position);
  * nothing is judged when fewer than 25 % of the seconds of the half count; a phase item needs 120 counted seconds, a count item 60 seconds with 8 or more, the side 60 player-seconds;
  * back line: L/4 or less from their goal line is low, L/3 or more is high; a class needs half of the seconds, and is said alone only when it leads the next class by 20 points
    (otherwise both are said: "낮은 편이었습니다(중간일 때도 많았습니다)"); the side needs half of the player-seconds;
  * width (10th to 90th percentile) 2W/3 or more is wide, length L/2 or more is long; narrow and short are never said (missed players make a team look narrower and shorter).
"""
from app.team_tactics import MIN_PLAYERS, shape

SEEN_MIN, SEEN_MAX, COUNT_MIN = MIN_PLAYERS, 11, 8
SHARE_MIN = 0.25
PHASE_SECONDS, COUNT_SECONDS, SIDE_POINTS = 120, 60, 60
CLASS_SHARE, SIDE_SHARE = 0.5, 0.5
CLASS_MARGIN = 0.2             # a class is said alone only when it leads the next one by 20 points or more (rules.md, added after the 11-20 check: it only says less)
COLS = 6
NOT_JUDGED = '상대가 충분히 보이지 않아 판단하지 않았습니다.'
SIDE_WORDS = {0: '우리 왼쪽', 1: '가운데', 2: '우리 오른쪽'}


def new_phase():
    return {'n': 0, 'n8': 0, 'width': 0.0, 'depth': 0.0, 'back': 0.0, 'front': 0.0, 'cls': [0, 0, 0], 'grid': [0] * (COLS * 3), 'cnt': [0] * (SEEN_MAX + 1)}


def new_opp():
    return {'n7': 0, 'n8': 0, 'd': new_phase(), 'a': new_phase(), 'lanes': [0, 0, 0]}


def _lane(v, width):
    return 0 if v < -width / 6 else 2 if v > width / 6 else 1


def add_second(opp, ours, theirs, length, width):
    """ours, theirs: [(u, v)] in our team's frame for one second (doubles merged). Adds into the bucket `opp` (new_opp())."""
    n = len(theirs)
    if n < SEEN_MIN or n > SEEN_MAX:
        return
    opp['n7'] += 1
    everyone = list(ours) + list(theirs)
    centre = sum(u for u, _ in everyone) / len(everyone)
    if centre == 0:
        return
    key = 'd' if centre > 0 else 'a'
    phase = opp[key]
    own = [(-u, -v) for u, v in theirs]                      # their own frame: towards our goal, their left negative
    s = shape(own)
    if s is None:
        return
    phase['n'] += 1
    phase['width'] += s['width']
    phase['depth'] += s['depth']
    phase['back'] += -s['back']                              # back in our frame (u)
    phase['front'] += -s['front']
    line = s['back'] + length / 2                            # distance of their back line from their own goal line
    phase['cls'][0 if line <= length / 4 else 2 if line >= length / 3 else 1] += 1
    for u, v in theirs:
        col = min(COLS - 1, max(0, int((u + length / 2) / (length / COLS))))
        phase['grid'][col * 3 + _lane(v, width)] += 1
    if key == 'a':
        for u, v in theirs:
            if u <= -length / 2 + length / 3:
                opp['lanes'][_lane(v, width)] += 1
    if n >= COUNT_MIN:
        opp['n8'] += 1
        phase['n8'] += 1
        ahead = sum(1 for u, _ in theirs if (u <= -length / 2 + length / 3 if key == 'a' else u < 0))
        phase['cnt'][min(ahead, SEEN_MAX)] += 1


def _sum_phase(phases):
    out = new_phase()
    for p in phases:
        for k in ('n', 'n8', 'width', 'depth', 'back', 'front'):
            out[k] += p[k]
        for k in ('cls', 'grid', 'cnt'):
            out[k] = [a + b for a, b in zip(out[k], p[k])]
    return out


def _median(hist):
    total = sum(hist)
    run = 0
    for i, c in enumerate(hist):
        run += c
        if 2 * run >= total:
            return i
    return 0


def _seen_word(share):
    return '전반 대부분' if share >= 0.75 else '전반의 절반 이상' if share >= 0.5 else '전반의 1/4 이상' if share >= SHARE_MIN else '전반의 1/4 미만'


def summary(buckets, length=89.0, width=62.0, half=1, entry_side=None):
    """The other team's block of the report from the minute buckets (dicts with 'n' and maybe 'opp'). Never raises for missing data.
    entry_side: the side the existing line "상대가 들어온 곳" names (0, 1, 2; -1 when it names none; None when it has too few entries). A side is said only when it agrees,
    so that the page never names two different sides (11-20 check, results.md)."""
    word = '전반' if half == 1 else '후반'
    opps = [b['opp'] for b in buckets if isinstance(b.get('opp'), dict)]
    seconds = sum(b.get('n', 0) for b in buckets)
    n7 = sum(o['n7'] for o in opps)
    share = n7 / seconds if seconds else 0.0
    seen_text = f'상대가 충분히 보인 시간: {_seen_word(share).replace("전반", word)}'
    titles = {'line': '수비 줄 높이', 'shape_defend': '지킬 때 모양', 'shape_attack': '공격할 때 모양', 'lanes': '들어온 쪽', 'numbers': '앞에 둔 선수'}
    if not opps or share < SHARE_MIN:
        return {'judged': False, 'seen_text': seen_text, 'headline': [NOT_JUDGED], 'shape': {'defend': None, 'attack': None}, 'lanes': None,
                'items': [{'key': k, 'title': t, 'text': NOT_JUDGED, 'judged': False} for k, t in titles.items()]}
    d = _sum_phase([o['d'] for o in opps])
    a = _sum_phase([o['a'] for o in opps])
    lanes = [sum(o['lanes'][i] for o in opps) for i in range(3)]
    items, headline = [], []

    # back line when they defended
    hedged = None
    if d['n'] >= PHASE_SECONDS:
        order = sorted(range(3), key=lambda i: -d['cls'][i])
        cls, second = order[0], order[1]
        close = (d['cls'][cls] - d['cls'][second]) / d['n'] < CLASS_MARGIN
        if d['cls'][cls] / d['n'] >= CLASS_SHARE and close:                    # the most common class is not clearly ahead of the next one: both are said (rules.md, added rule)
            text = ['상대 수비 줄은 낮은 편이었습니다', '상대 수비 줄은 가운데쯤이었습니다', '상대 수비 줄은 높은 편이었습니다'][cls] + \
                   ['(낮을 때도 많았습니다).', '(중간일 때도 많았습니다).', '(높을 때도 많았습니다).'][second]
            hedged = text
        elif d['cls'][cls] / d['n'] >= CLASS_SHARE:
            text = ['상대 수비 줄이 낮았습니다(자기 박스 가까이). 수비 뒤 공간이 좁았습니다.', '상대 수비 줄은 가운데쯤(자기 진영 중간)에 있었습니다.',
                    '상대 수비 줄이 높았습니다(중앙선 쪽). 수비 뒤 공간이 있었습니다.'][cls]
            headline.append(['상대는 수비 줄을 낮게 내렸고', '상대 수비 줄은 가운데쯤이었고', '상대는 수비 줄을 높이 올렸고'][cls])
        else:
            text = '상대 수비 줄의 높이가 자주 바뀌었습니다.'
        items.append({'key': 'line', 'title': titles['line'], 'text': text, 'judged': True})
    else:
        items.append({'key': 'line', 'title': titles['line'], 'text': NOT_JUDGED, 'judged': False})

    # where they stood, and how wide and long, in each phase
    pictures = {}
    for key, p, name in (('defend', d, '지킬 때'), ('attack', a, '공격할 때')):
        if p['n'] < PHASE_SECONDS:
            pictures[key] = None
            items.append({'key': f'shape_{key}', 'title': titles[f'shape_{key}'], 'text': NOT_JUDGED, 'judged': False})
            continue
        total = sum(p['grid']) or 1
        pictures[key] = {'grid': [round(c / total, 3) for c in p['grid']], 'back_u': round(p['back'] / p['n'], 1), 'front_u': round(p['front'] / p['n'], 1)}
        # missed players only make the team look narrower and shorter, so only "wide" and "long" are said (11-20 check: "short" was wrong, results.md)
        w, dep = p['width'] / p['n'], p['depth'] / p['n']
        said = [text for ok, text in ((w >= 2 * width / 3, '옆으로 넓게 벌렸습니다'), (dep >= length / 2, '위아래로 길게 늘어졌습니다')) if ok]
        text = f'{name} ' + (', '.join(said) + '.' if said else '폭과 길이에 눈에 띄는 점은 없었습니다.')
        items.append({'key': f'shape_{key}', 'title': titles[f'shape_{key}'], 'text': text, 'judged': True})

    # the side they came in on
    lane_block = None
    if sum(lanes) >= SIDE_POINTS:
        shares = [c / sum(lanes) for c in lanes]
        best = max(range(3), key=lambda i: shares[i])
        main = best if shares[best] >= SIDE_SHARE else None
        unclear = main is not None and entry_side is not None and entry_side != main    # the moments they came in (entries) point elsewhere: no side is said
        main = None if unclear else main
        lane_block = {'shares': [round(s, 3) for s in shares], 'main': main, 'unclear': main is None}   # unclear: the page dims the bars so they are not read as a side
        if unclear:
            text = '상대가 들어온 쪽은 분명하지 않았습니다(들어오는 순간과 머문 곳이 달랐습니다).'
        elif main is None:
            text = '상대가 들어오는 쪽은 한쪽에 몰리지 않았습니다.'
        else:
            text = f'상대는 주로 {SIDE_WORDS[main]}{"로" if main == 1 else "으로"} 들어왔습니다.'
            headline.append(f'주로 {SIDE_WORDS[main]}{"로" if main == 1 else "으로"} 들어왔습니다')
        items.append({'key': 'lanes', 'title': titles['lanes'], 'text': text, 'judged': True})
    else:
        items.append({'key': 'lanes', 'title': titles['lanes'], 'text': NOT_JUDGED, 'judged': False})

    # how many they sent forward / left up front
    parts = []
    if a['n8'] >= COUNT_SECONDS:
        k = _median(a['cnt'])
        parts.append(f'공격할 때 우리 수비 지역까지 {k}명 안팎이 올라왔습니다.' if k else '공격할 때 우리 수비 지역까지 올라온 선수는 거의 없었습니다.')
    if d['n8'] >= COUNT_SECONDS:
        k = _median(d['cnt'])
        parts.append(f'지킬 때 우리 진영에 {k}명 안팎을 남겼습니다(역습 대비).' if k else '지킬 때 거의 모두 자기 진영으로 내려왔습니다.')
    items.append({'key': 'numbers', 'title': titles['numbers'], 'text': ' '.join(parts) if parts else NOT_JUDGED, 'judged': bool(parts)})

    if hedged:
        head = [hedged] + [f'상대는 {h}.' for h in headline]
    elif len(headline) == 2:
        head = [f'{headline[0]}, {headline[1]}.']
    elif headline and headline[0].endswith('고'):
        head = [headline[0][:-1] + '습니다.']
    elif headline:
        head = [f'상대는 {headline[0]}.']
    else:
        head = ['상대가 한쪽으로 몰리거나 수비 줄 높이가 분명하게 드러나지는 않았습니다.']
    return {'judged': True, 'seen_text': seen_text, 'headline': head, 'shape': pictures, 'lanes': lane_block, 'items': items}
