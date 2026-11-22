"""The words of the review video: short captions during a sequence, a specific analysis, the rules a player can act on and one training drill.

The wording is football talk, specific to the moment (the side of the pitch, how many defenders were close, how high the opponent line stood, how many
teammates supported) and written for the player: what to do, how to train it. Numbers appear as head counts, speeds a coach understands (km/h) and the
sizes of a drill. Nothing here talks about the limits of the data; those belong in the operating guide.
"""

SIDE = {'near': '가까운 쪽 측면', 'far': '먼 쪽 측면', 'centre': '중앙'}


def _block(back_line):
    if back_line >= 30:
        return '상대는 골문 앞에 낮게 내려앉아 있었습니다'
    if back_line < 15:
        return '상대가 라인을 높게 올려 뒷공간이 열려 있었습니다'
    return '상대는 중간 높이로 라인을 세웠습니다'


def _count(n):
    return {1: '한 명', 2: '두 명', 3: '세 명', 4: '네 명'}.get(n, f'{n}명')


def event_bullets(event, context):
    """Three short bullets (kept as a fallback). context: side, back_line, between, box_ours."""
    side = SIDE.get(context.get('side'))
    where = f'{side}에서 ' if side else ''
    kind = event['kind']
    block = _block(context.get('back_line', 20))
    if kind == 'box_attack':
        return [f'{where}박스 안으로 사람이 여럿 들어갔습니다', block, '마무리 선택지를 두 개 이상 만들어 보세요']
    if kind == 'run':
        second = '라인 사이에서 받아 주는 선수가 함께 있었습니다' if context.get('between', 0) >= 2 else '상대 수비가 뒤로 물러서야 했습니다'
        return [f'{where}수비 라인 뒤로 먼저 출발했습니다', second, '다음에는 이 타이밍에 패스가 나오도록 맞춰 보세요']
    if kind == 'conceded_run':
        return [f'{where}상대가 우리 수비 라인 뒤로 달려 들어갔습니다', '라인이 함께 내려가지 못해 뒷공간이 비었습니다', '먼저 따라붙는 선수와 라인을 맞추는 신호를 정해 두세요']
    if kind == 'isolated':
        return ['가장 앞선 선수가 혼자 떨어져 있었습니다', '가까운 지원이 없어 공을 지키기 어려웠습니다', '미드필더가 가까이 올라가 지원 각도를 만들어 주세요']
    if kind == 'line_drop':
        return ['수비 라인이 골문 쪽으로 크게 내려앉았습니다', '중원과 간격이 벌어져 공간을 내줬습니다', '라인을 같이 올리고 내리는 신호를 정해 두세요']
    finish = '박스 안에 우리 선수가 여럿 들어가 마무리 숫자가 충분했습니다' if context.get('box_ours', 0) >= 3 else '박스 안 인원이 적었는데도 골로 이어졌습니다' if context.get('box_ours', 9) <= 1 else '마무리까지 이어진 좋은 공격이었습니다'
    return [f'{where}올라가 골로 마무리했습니다', block, finish]


def index_title(event, clock):
    """One line of the chapter list."""
    return event['title'] + (' · 골로 이어짐' if event.get('goal_follow') and event['kind'] != 'goal' else '')


def captions(event, facts):
    """Subtitles for the sequence: [(seconds after the moment, seconds shown, text)]. Negative offsets come before the moment."""
    side = SIDE.get(facts.get('side'))
    where = f'{side}에서 ' if side else ''
    kind = event['kind']
    near = facts.get('defenders_near', 0)
    out = []
    if kind == 'box_attack':
        out = [(-2.0, 2.5, f'{where}공격이 박스 쪽으로 올라갑니다'), (0.5, 3.0, f'박스 안에 우리 선수가 {_count(facts.get("box_ours", 0))} 있습니다' if facts.get('box_ours') else '박스 쪽으로 사람이 모입니다')]
    elif kind == 'run':
        out = [(-2.5, 2.5, f'{where}수비 라인을 보며 출발합니다'), (0.0, 3.0, '수비 라인 뒤 공간으로 들어갑니다' + (f' · 수비수 {_count(near)}이 가까이 있습니다' if near else ''))]
    elif kind == 'conceded_run':
        out = [(-2.5, 2.5, f'{where}상대가 우리 라인을 보며 출발합니다'), (0.0, 3.0, '우리 수비 라인 뒤로 들어옵니다' + (f' · 가까이 있던 우리 수비수는 {_count(near)}' if near else ''))]
    elif kind == 'isolated':
        out = [(-3.0, 3.0, '가장 앞선 선수가 홀로 올라가 있습니다'), (0.5, 3.0, f'가까이 있는 상대 수비수는 {_count(near)}입니다' if near else '주변에 지원하는 동료가 없습니다')]
    elif kind == 'line_drop':
        out = [(-3.0, 3.0, '수비 라인이 천천히 내려앉습니다'), (0.5, 3.0, '중원과의 간격이 벌어집니다')]
    elif kind == 'goal':
        out = [(-3.0, 3.0, f'{where}공격이 올라갑니다'), (0.5, 3.0, '박스 쪽으로 사람이 모입니다')]
    if event.get('goal_at') is not None:
        out.append((event['goal_at'] - event['time'] - 2.5, 2.5, '마무리까지 이어집니다'))
        out.append((event['goal_at'] - event['time'] - 0.2, 2.2, '골'))
    elif kind in ('run', 'isolated', 'goal', 'box_attack'):
        out.append((4.0, 3.0, '공격이 이어집니다'))
    return out


def analysis(event, facts):
    """The analysis card of a moment: a one-line summary, what went well, what to fix and one thing to do next (each a short sentence)."""
    side = SIDE.get(facts.get('side'))
    where = f'{side}에서 ' if side else ''
    kind = event['kind']
    near, support = facts.get('defenders_near', 0), facts.get('support_near', 0)
    block = _block(facts.get('back_line', 20))
    speed = facts.get('speed_kmh')
    finish = facts.get('box_ours', 0)
    to_goal = event.get('goal_follow') or kind == 'goal'
    if kind == 'box_attack':
        good = [f'{where}올라간 공격에서 박스 안에 우리 선수가 {_count(finish)} 들어갔습니다', block]
        fix = []
        if facts.get('box_theirs', 0) >= finish + 2:
            fix.append('박스 안 상대 수비수가 우리보다 많았습니다')
        if finish <= 3:
            fix.append('박스 안 인원을 한 명 더 늘리면 마무리 선택지가 많아집니다')
        fix.append('들어간 선수들이 한곳에 몰리지 않고 가까운 포스트, 먼 포스트, 컷백 자리로 나뉘는지 보세요')
        summary = f'{where}박스 안으로 사람이 모인 공격' + (' → 골로 마무리' if to_goal else '')
        nxt = '공이 측면에 있을 때 박스 안 세 자리(가까운 포스트, 먼 포스트, 뒤쪽)를 나눠 서는 약속을 정하세요'
    elif kind == 'run':
        good = [f'{where}수비 라인을 넘어서는 침투였습니다' + (f' (순간 속도 약 {speed}km/h)' if speed else ''), block]
        if support >= 2:
            good.append(f'가까이 동료가 {_count(support)} 있어 연결 선택지가 있었습니다')
        fix = []
        if near >= 2:
            fix.append(f'수비수 {_count(near)}이 가까이 있어 슈팅 공간이 좁았습니다')
        if to_goal and finish <= 1:
            fix.append('마무리 순간 박스 안 인원이 적었습니다')
        fix.append('침투한 뒤 옆으로 내줄 두 번째 선택지를 만들면 더 위협적입니다')
        summary = f'{where}수비 라인 뒤로 먼저 출발한 침투' + (' → 골로 마무리' if to_goal else '')
        nxt = '출발 신호와 패스 타이밍을 맞추는 훈련을 반복해 보세요'
    elif kind == 'conceded_run':
        good = ['상대 움직임이 또렷이 보이는 장면이라 훈련 소재로 좋습니다']
        fix = [f'{where}상대가 우리 수비 라인 뒤로 들어오는 동안 라인이 함께 내려가지 못했습니다', f'가까이 있던 우리 수비수가 {_count(near)}뿐이었습니다' if near else '가까이 따라붙는 수비수가 없었습니다']
        summary = '상대 침투를 허용한 장면'
        nxt = '라인을 올릴지 내릴지 한 명이 신호를 주고, 가장 가까운 수비수가 먼저 따라붙는 약속을 정하세요'
    elif kind == 'isolated':
        good = ['공격 라인이 상대 진영 깊숙이 올라가 있었습니다']
        fix = ['가장 앞선 선수에게 가까운 지원이 없었습니다', f'주변 상대 수비수는 {_count(near)}이었습니다' if near else '공을 받아도 이어 갈 선택지가 적었습니다']
        summary = '앞선 선수가 홀로 남은 장면'
        nxt = '미드필더 한 명이 공격수 뒤 15미터 안쪽으로 올라가 지원 각도를 만드세요'
    elif kind == 'line_drop':
        good = ['수비 라인이 서로 간격을 맞추며 함께 움직였습니다']
        fix = ['라인이 골문 쪽으로 깊이 내려앉아 중원과 간격이 벌어졌습니다', '그 사이 공간을 상대에게 내줄 수 있습니다']
        summary = '수비 라인이 크게 내려앉은 장면'
        nxt = '내려앉는 순간 중원 선수가 함께 내려와 간격을 줄이는 신호를 정해 두세요'
    else:
        good = [f'{where}올라가 골로 마무리한 공격입니다', block]
        if finish >= 3:
            good.append(f'박스 안에 우리 선수가 {_count(finish)} 들어가 있었습니다')
        fix = []
        if finish <= 1:
            fix.append('박스 안 인원이 적었는데도 마무리가 됐습니다. 숫자를 더 넣으면 더 안정적입니다')
        summary = '골로 이어진 공격'
        nxt = '같은 구조를 다른 쪽 측면에서도 만들어 보세요'
        if not fix:
            fix = ['골이 나온 쪽 말고 반대편에도 선택지가 있었는지 영상으로 같이 확인해 보세요']
    return {'summary': summary, 'good': good[:3], 'fix': fix[:3], 'next': nxt}


def coaching(event, facts):
    """What a player can act on: three rules from the player's point of view and one drill with its set-up. Used for strengths (repeat it) and weaknesses (fix it)."""
    kind = event['kind']
    near = facts.get('defenders_near', 0)
    if kind == 'box_attack':
        return {'title': '박스 안으로 들어가는 선수의 행동 수칙',
                'rules': ['공이 측면에 있으면 반대편 선수도 늦지 않게 박스 쪽으로 대각선으로 들어갑니다', '박스 안에서는 가까운 포스트, 먼 포스트, 뒤쪽 자리를 나눠 서서 한곳에 몰리지 않습니다',
                          '크로스나 컷백이 올 때 수비수 뒤에서 앞으로 달려 들어가며 첫 터치로 바로 마무리합니다'],
                'drill': {'name': '박스 진입 5대4', 'setup': ['하프코트 한쪽, 공격 5명과 수비 4명, 골키퍼 포함', '측면에서 시작하고 박스 안에 공격수 세 명이 들어간 뒤에만 크로스나 컷백을 허용'],
                          'focus': '박스 진입 타이밍과 서는 자리 나누기'}}
    if kind == 'run':
        return {'title': '침투하는 선수의 행동 수칙',
                'rules': ['출발 전에 어깨 너머로 수비 라인의 높이와 공을 가진 선수를 함께 봅니다', '라인이 올라오는 순간 한 박자 먼저 출발하고, 공 가진 선수에게 손이나 목소리로 신호를 줍니다',
                          '수비수를 앞질렀다면 수비수와 골문 사이로 들어가고, 바로 슈팅이나 옆 선택지를 정합니다'],
                'drill': {'name': '라인 침투 3대2 게임', 'setup': ['25미터 x 30미터 구역, 공격 3명과 수비 2명, 수비 라인 뒤에 골문 하나', '공격은 수비 라인이 올라오는 순간에만 침투 패스를 넣을 수 있음'],
                          'focus': '출발 신호와 첫 터치 방향'}}
    if kind == 'conceded_run':
        return {'title': '수비 라인의 행동 수칙',
                'rules': ['라인을 지킬 때는 공이 아니라 라인의 옆 선수와 상대 공격수를 함께 봅니다', '라인을 올릴지 내릴지 한 명(가운데 수비수)이 큰 소리로 신호를 주고 모두 같이 움직입니다',
                          '뒤로 뛰어드는 상대가 있으면 가장 가까운 수비수가 먼저 따라붙고 나머지는 라인을 내립니다'],
                'drill': {'name': '라인 맞추기 4대3', 'setup': ['30미터 x 30미터 구역, 수비 4명 라인과 공격 3명', '공을 가진 공격수가 고개를 드는 순간 수비가 신호에 맞춰 라인을 올리거나 내림'],
                          'focus': '신호 소리와 따라붙는 첫 걸음'}}
    if kind == 'isolated':
        return {'title': '앞선 선수와 지원 선수의 행동 수칙',
                'rules': ['앞선 선수는 공을 받기 전에 지원이 올라올 때까지 한 박자 기다리거나 안쪽으로 내려와 받습니다', '미드필더는 공이 앞으로 가는 순간 공격수 뒤 15미터 안쪽으로 따라 올라갑니다',
                          '공을 잃어도 가까운 선수가 바로 압박해 되찾을 수 있는 간격을 유지합니다' + (f' (현재 주변 상대 수비수 {_count(near)})' if near else '')],
                'drill': {'name': '지원 거리 유지 3대3', 'setup': ['20미터 x 30미터 구역, 3대3과 골대 두 개', '공을 받은 공격수 주변 15미터 안에 동료가 항상 한 명 이상 있어야 득점으로 인정'],
                          'focus': '공이 앞으로 가는 순간 따라 올라가는 타이밍'}}
    if kind == 'line_drop':
        return {'title': '라인 간격을 지키는 행동 수칙',
                'rules': ['수비 라인이 내려가면 중원 선수도 같이 내려와 두 라인 사이를 15미터 안쪽으로 유지합니다', '라인을 내릴 때는 한꺼번에, 같은 속도로 움직이고 가운데 수비수가 신호를 줍니다',
                          '상대가 공을 잡은 순간 압박할 선수를 정하고, 나머지는 공간을 막는 위치로 이동합니다'],
                'drill': {'name': '라인 간격 유지 훈련', 'setup': ['수비 4명과 중원 3명이 40미터 구역에서 공의 위치에 맞춰 함께 올라가고 내려가기', '감독이 신호를 주면 라인 사이 거리를 줄 하나로 확인'],
                          'focus': '두 라인 사이 거리와 이동 속도'}}
    return {'title': '득점으로 이어진 공격의 행동 수칙',
            'rules': ['공을 가진 선수는 고개를 들어 수비 라인과 동료의 침투를 먼저 확인합니다', '측면이나 안쪽에서 받는 선수와 뒤로 침투하는 선수를 동시에 만들어 수비를 두 방향으로 묶습니다',
                      '마무리 순간에는 박스 안에 최소 세 명이 들어가 있도록 반대편 선수도 늦지 않게 들어갑니다'],
            'drill': {'name': '마무리 숫자 맞추기 5대4', 'setup': ['하프코트 한쪽, 공격 5명과 수비 4명, 골키퍼 포함', '득점은 박스 안에 공격수 세 명이 있을 때만 인정, 측면에서 시작'],
                      'focus': '반대편 선수와 2선 선수의 박스 진입 타이밍'}}


def half_summary(events):
    """The points of a whole half from the moments found: counts and what to take from them (short bullets)."""
    count = lambda kind: sum(1 for e in events if e['kind'] == kind)
    runs = [e for e in events if e['kind'] == 'run']
    scored = sum(1 for e in runs if e.get('goal_follow'))
    boxes = [e for e in events if e['kind'] == 'box_attack']
    points = []
    if boxes:
        points.append(f'박스 안으로 사람이 모인 공격이 {len(boxes)}번 있었고 그중 {sum(1 for e in boxes if e.get("goal_follow"))}번이 골로 이어졌습니다')
    if runs or count('goal'):
        points.append(f'침투가 {len(runs)}번 보였고 그중 {scored}번이 골로 이어졌습니다' if runs else f'골 {count("goal")}개가 모두 올라가는 공격에서 나왔습니다')
    if count('conceded_run'):
        points.append(f'상대 침투를 {count("conceded_run")}번 허용했습니다. 수비 라인을 맞추는 약속이 필요합니다')
    if count('isolated'):
        points.append('앞선 선수가 혼자 남는 장면이 있었습니다. 가까운 지원을 만드세요')
    if count('line_drop'):
        points.append('수비 라인이 크게 내려앉는 순간이 있었습니다. 중원과 간격을 지키세요')
    return points or ['이 하프에서는 뚜렷한 패턴이 많지 않았습니다']


def attack_story(facts, to_goal):
    """How the attack was built and which passing lanes the team had, for a coach and the players. facts: from app.attack_options.analyse.
    A passing lane is open when no opponent stands next to the line of the pass. For a goal the card is mostly what worked (at most one thing to look at);
    for an attack that did not end in a goal it explains why: which lanes were blocked, which were open (above all across the pitch) and what the player could have done.
    Returns {'summary', 'good', 'fix', 'next'}."""
    side = SIDE.get(facts.get('side'), '중앙')
    who = '공을 가진 선수' if facts.get('carrier_source') == 'given' else '앞선 선수'
    lanes = facts.get('lanes') or []
    across = [l for l in lanes if l['open'] and l['across']]
    forward_open = [l for l in lanes if l['open'] and l['forward'] and not l['across']]
    forward_blocked = [l for l in lanes if not l['open'] and l['forward']]
    shift, width = facts.get('shift', 0.0), facts.get('width', 0.0)
    good = []
    if abs(shift) >= 12:
        good.append(f'공격하는 동안 팀의 무게중심이 옆으로 약 {int(abs(shift))}미터 이동해 공격 방향을 바꿨습니다')
    if width >= 38:
        good.append(f'상대 진영에서 좌우로 약 {int(width)}미터까지 벌려 서서 수비를 넓게 끌어냈습니다')
    if facts.get('goal_side', 9) <= 3 and facts.get('carrier_u', 0) < 30:          # a player already on the goal line has nothing ahead of him by definition
        good.append(f'{who} 앞에 상대 수비수가 적어 정면 돌파나 슈팅 공간이 있었습니다')
    if forward_open:
        good.append(f'{who}에게서 앞쪽 동료 {_count(len(forward_open))}으로 가는 패스길이 열려 있었습니다')
    if not good:
        good.append(f'{side}에서 시작한 공격이 상대 진영 깊숙이 이어졌습니다')
    fix = []
    if not to_goal:
        if forward_blocked:
            fix.append(f'{who} 앞쪽 패스길 {len(forward_blocked)}개는 수비수가 선 위에 있어 막혀 있었습니다. 막힌 길로 넣으면 공을 뺏기기 쉽습니다')
        if across:
            fix.append(f'반대편 동료에게 가는 패스길은 열려 있었습니다({len(across)}개). 고개를 들어 그쪽으로 크게 돌리면 수비를 옆으로 끌어낼 수 있습니다')
        elif forward_open:
            fix.append('앞쪽에 열린 패스길이 있었습니다. 슈팅이나 돌파를 정하기 전에 그 길을 먼저 확인해 보세요')
        elif not forward_blocked and lanes:
            closed = len([l for l in lanes if not l['open']])
            fix.append(f'{who}에게서 동료에게 가는 패스길 {closed}개가 모두 수비수 옆을 지나야 했습니다. 가까운 동료가 받을 각도를 만들어 주는 움직임이 필요했습니다')
        elif not lanes:
            fix.append('패스를 받을 수 있는 거리에 동료가 없었습니다. 지원하는 선수가 더 가까이 올라와야 했습니다')
        if facts.get('goal_side', 0) >= 5:
            fix.append(f'골문 쪽에 상대 수비수가 {_count(facts["goal_side"])} 있어 정면은 막혀 있었습니다. 옆이나 뒤로 돌려 공간을 만드는 선택이 필요했습니다')
    elif across and not forward_open:
        fix.append('이 공격에서는 반대편 패스길도 열려 있었습니다. 다음에는 그쪽도 함께 확인해 보세요')
    summary = ('골로 이어진 공격' if to_goal else '골이 나오지 못한 공격') + f': {side}에서 전개'
    nxt = '공을 받기 전 2초 동안 좌우 어깨 너머로 패스길이 열린 동료를 확인하는 습관을 들이세요'
    return {'summary': summary, 'good': good[:3], 'fix': fix[:3], 'next': nxt}


def attack_instructions(facts, is_goal):
    """'Move like this': what each player in the picture should do next time, from the passing lanes of the scene. Up to four lines 'role: instruction'."""
    lanes = facts.get('lanes') or []
    across = [l for l in lanes if l['open'] and l['across']]
    forward_open = [l for l in lanes if l['open'] and l['forward'] and not l['across']]
    blocked = [l for l in lanes if not l['open']]
    who = '공을 가진 선수' if facts.get('carrier_source') == 'given' else '앞선 선수'
    out = []
    if across:
        out.append(f'{who}: 정면이 막혀 있으면 한 번에 반대편 열린 동료({len(across)}명)에게 크게 돌려 수비를 옆으로 끌어냅니다')
    elif forward_open:
        out.append(f'{who}: 열린 앞쪽 패스길의 동료({len(forward_open)}명)에게 받을 발 쪽으로 바로 넣습니다')
    elif blocked:
        out.append(f'{who}: 막힌 길로 넣지 말고 몸으로 공을 지키며 동료가 각도를 만들 때까지 한 박자 기다립니다')
    else:
        out.append(f'{who}: 받기 전에 어깨 너머로 주변 동료 위치를 보고 첫 터치 방향을 정합니다')
    if blocked:
        out.append(f'막힌 길의 동료({len(blocked)}명): 수비수 뒤나 옆으로 3~4미터 움직여 패스가 지나갈 각도를 만들고, 받기 직전에 손으로 신호를 줍니다')
    if across:
        out.append('반대편 동료: 폭을 유지해 선 채로 공이 오기 전에 손으로 신호를 주고, 받으면 바로 앞을 봅니다')
    if is_goal:
        out.append('박스 안 선수: 가까운 포스트, 먼 포스트, 뒤쪽 자리를 나눠 서서 같은 움직임이 다시 나오도록 합니다')
    else:
        out.append('앞선 선수 옆 선수: 공 가진 선수와 15미터 안에서 지원 각도를 만들어 혼자 남지 않게 합니다')
    return out[:4]
