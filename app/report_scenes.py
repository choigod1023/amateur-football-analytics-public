"""Pick the scenes of a video report for one team and write the coaching text, from player positions in metres only.

There is no ball in this data. A scene is therefore a stretch in which the team stood and moved in a way that matters for
attacking play (how far it was up the pitch, whether lanes through the opponent's back line were open, whether a player stood
between the opponent's lines, whether the most advanced player was alone), not a stretch in which the team had the ball.
The coordinate `u` is metres toward the goal the focus team attacks (u > 0 is the opponent half).
Phases follow the common analyst split: build-up (own third), progression (middle third), final third (the last third).
"""
import math

from app.tactical_feedback import open_lanes, team_lines

THIRD = 89.0 / 6          # half the length of a third of the pitch; the thirds are cut at u = -THIRD and +THIRD


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def second_metrics(team, opponents, direction=1, minimum=7):
    """Numbers of one moment. team / opponents: [(track id, x, y)]; direction: +1 when the focus team attacks toward +x.

    Returns None when either side has fewer than `minimum` players (7 normally; the lines need at least 6) or the lines cannot be told. The opponent back line is the
    mean depth of its deepest group (see team_lines); a lane breaks the line when it starts in front of that line and ends level
    with or behind it; a player is 'between the lines' when he stands between the opponent midfield and back line."""
    if len(team) < minimum or len(opponents) < minimum:
        return None
    mine = [(x * direction, y) for _, x, y in team]
    theirs = [(x * direction, y) for _, x, y in opponents]
    own_lines = team_lines(mine, 1)
    opp_lines = team_lines([(-u, y) for u, y in theirs], 1)      # the opponent looks the other way
    if not own_lines or not opp_lines:
        return None
    opp_back, opp_mid = -opp_lines['defence'], -opp_lines['midfield']
    lanes = open_lanes(mine, theirs, 1)
    breaking = [l for l in lanes if mine[l['from']][0] < opp_back <= mine[l['to']][0]]
    between = [team[i][0] for i, (u, _) in enumerate(mine) if opp_mid < u < opp_back]
    outfield = sorted(range(len(mine)), key=lambda i: -mine[i][0])
    lead = outfield[1] if len(outfield) > 8 and mine[outfield[0]][0] > opp_back + 10 else outfield[0]     # a far goalkeeper of the other team is not the leader
    others = [m for i, m in enumerate(mine) if i != lead]
    isolation = min(_distance(mine[lead], o) for o in others)
    return {'centre': sum(u for u, _ in mine) / len(mine), 'ahead': sum(1 for u, _ in mine if u > 0), 'forward_lanes': sum(1 for l in lanes if l['forward']),
            'line_breaking': len(breaking), 'between': between, 'attack_line': own_lines['attack'], 'middle_line': own_lines['midfield'],
            'defence_line': own_lines['defence'], 'opponent_back_line': opp_back, 'gap_mid_attack': own_lines['midfield_to_attack'],
            'leader': team[lead][0], 'leader_isolation': isolation, 'width': max(y for _, y in mine) - min(y for _, y in mine),
            'lane_pairs': [(team[l['from']][0], team[l['to']][0]) for l in breaking[:3]]}


def phase_of(centre):
    """build-up, progression or final third by where the team stands (centre of the players, metres toward the opponent goal)."""
    if centre < -THIRD:
        return 'build_up'
    return 'progression' if centre < THIRD else 'final_third'


def window_scores(series, window=15):
    """series: {second: metrics}. Scores of every window of `window` seconds that has at least 70 % of its seconds measured.

    good: lanes through the opponent back line, players between the lines and the attack line pushed beyond the opponent back line.
    poor: the team is up the pitch while its leader stands alone (far from every teammate) and few lanes lead forward.
    Returns [{'start', 'end', 'good', 'poor', 'phase', 'n'}]."""
    scores = []
    for start in sorted(series):
        seconds = [series[s] for s in range(start, start + window) if s in series]
        if len(seconds) < 0.7 * window:
            continue
        mean = lambda key: sum(m[key] for m in seconds) / len(seconds)
        between = sum(len(m['between']) for m in seconds) / len(seconds)
        up = mean('centre') > -5
        good = mean('line_breaking') + 0.6 * between + max(0.0, (mean('attack_line') - mean('opponent_back_line') + 3)) / 5
        poor = (max(0.0, mean('leader_isolation') - 12) / 4 + max(0.0, 8 - mean('forward_lanes')) / 3) if up else 0.0
        scores.append({'start': start, 'end': start + window, 'good': round(float(good), 2), 'poor': round(float(poor), 2), 'phase': phase_of(mean('centre')), 'n': len(seconds),
                       'means': {k: round(float(mean(k)), 1) for k in ('centre', 'forward_lanes', 'line_breaking', 'leader_isolation', 'gap_mid_attack', 'attack_line', 'opponent_back_line', 'width')} | {'between': round(float(between), 1)}})
    return scores


def pick_windows(scores, key, count=3, spacing=40, minimum=0.5):
    """The best `count` windows by `key` ('good' or 'poor'), at least `spacing` seconds apart, each scoring at least `minimum`."""
    chosen = []
    for item in sorted(scores, key=lambda s: -s[key]):
        if item[key] >= minimum and all(abs(item['start'] - c['start']) >= spacing for c in chosen):
            chosen.append(item)
        if len(chosen) == count:
            break
    return sorted(chosen, key=lambda s: s['start'])


def key_player(series, window, kind):
    """Track id of the player to highlight in a window: for a good scene the player who stood between the opponent lines most often
    (the lane receiver), for a poor scene the leader who stood alone most often. None when nobody stands out (fewer than 4 seconds)."""
    counts = {}
    for s in range(window['start'], window['end']):
        metrics = series.get(s)
        if not metrics:
            continue
        who = metrics['between'] if kind == 'good' else ([metrics['leader']] if metrics['leader_isolation'] > 12 else [])
        for tid in who:
            counts[tid] = counts.get(tid, 0) + 1
    if not counts:
        return None
    tid, n = max(counts.items(), key=lambda kv: kv[1])
    return tid if n >= 4 else None


PHASE_NAMES = {'build_up': '빌드업(우리 진영 3분의 1)', 'progression': '전진(중간 3분의 1)', 'final_third': '마무리(상대 진영 3분의 1)'}


SIDE_WORDS = {'near': '카메라에서 가까운 쪽 측면', 'far': '카메라에서 먼 쪽 측면', 'centre': '중앙'}


def analysis_sentences(window):
    """Football wording for what the positions of a scene show: (strengths, cautions, advice). No numbers beyond head counts."""
    m = window['means']
    strengths, cautions, advice = [], [], []
    back = m['opponent_back_line']
    if back >= 30:
        block = '상대는 수비 라인을 골문 가까이 내리고 촘촘하게 버티는 낮은 블록이었습니다.'
        advice.append('낮은 블록을 상대할 때는 측면에서 크로스, 2선에서 들어오는 침투, 박스 앞 중거리 슈팅으로 변화를 주면 틈이 생깁니다.')
    elif back >= 15:
        block = '상대는 중간 높이에서 수비 라인을 유지했습니다.'
    else:
        block = '상대가 수비 라인을 높이 올려 뒷공간이 크게 열려 있었습니다.'
        advice.append('상대 라인이 높을 때는 수비 뒤로 넘기는 패스와 빠른 침투가 가장 효과적이므로, 공격수가 오프사이드 라인을 보며 타이밍을 맞춰야 합니다.')
    strengths.append(block) if back < 15 else None
    if m['attack_line'] >= back:
        strengths.append('우리 공격 라인이 상대 수비 라인과 같은 높이까지 올라가 수비를 뒤로 밀어 냈습니다.')
    elif m['attack_line'] < back - 10:
        cautions.append('공격 라인이 상대 수비 라인과 거리가 있어서 상대가 편하게 라인을 유지할 수 있었습니다.')
    if m['centre'] >= 12:
        strengths.append('우리 팀 전체가 상대 진영 깊숙이 올라가 압박과 세컨드볼을 잡기 좋은 위치였습니다.')
    elif m['centre'] < 0:
        cautions.append('팀 전체가 아직 우리 진영에 가까워서, 공을 잃으면 상대가 빠르게 역습할 공간이 있었습니다.')
    if m['between'] >= 2:
        strengths.append('미드필더와 수비수 사이 공간에서 공을 받으려는 선수가 두 명 이상 있어 상대 수비가 한쪽으로만 대응하기 어려웠습니다.')
    elif m['between'] < 1:
        cautions.append('상대 라인 사이에서 받아 주는 선수가 거의 없어서 공이 앞으로 가려면 측면 길밖에 없었습니다.')
        advice.append('한 명이 상대 미드필더와 수비수 사이로 내려와 받아 주고, 다른 한 명이 수비 뒤로 들어가 상대를 두 방향으로 묶는 움직임이 필요합니다.')
    if m['line_breaking'] >= 1.5:
        strengths.append('수비 뒤로 찌를 수 있는 열린 길, 즉 킬 패스를 넣을 길이 여러 군데 있어 어디로든 공을 넣을 수 있는 구조였습니다.')
    elif m['line_breaking'] < 0.5:
        cautions.append('상대 수비 뒤로 향하는 길이 대부분 막혀 있었습니다.')
    if m['leader_isolation'] <= 8:
        strengths.append('가장 앞선 선수 가까이에 동료가 있어서 연결과 지원이 쉬웠습니다.')
    elif m['leader_isolation'] > 14:
        cautions.append('가장 앞선 선수가 동료와 멀리 떨어져 혼자 싸우는 모양이었습니다.')
        advice.append('앞선 선수가 혼자 기다리지 않도록 미드필더 한 명이 가까운 거리에서 지원 각도를 만들어야 하고, 그래야 공을 잃어도 바로 압박할 수 있습니다.')
    if m['width'] >= 38:
        strengths.append('측면까지 넓게 벌려 상대 수비를 옆으로 늘렸습니다.')
    elif m['width'] <= 26:
        cautions.append('선수들이 좁게 모여서 상대 수비가 중앙에 집중하기 쉬웠습니다.')
        advice.append('반대편 측면 선수가 넓게 벌려서 상대 수비를 옆으로 늘려 주면 중앙에 공간이 생깁니다.')
    events = window.get('events') or {}
    zone_words = {'wing': '측면', 'half_space': '하프스페이스', 'centre': '중원'}
    runs = events.get('runs') or []
    if runs:
        strengths.append('수비 라인 뒤로 달려 들어가는 침투가 나와서 상대 수비가 뒤로 물러서야 했습니다.' if len(runs) == 1 else '수비 라인 뒤로 달려 들어가는 침투가 여러 번 나와서 상대 수비가 계속 뒤로 물러서야 했습니다.')
    elif events.get('measured_runs'):
        cautions.append('수비 라인 뒤로 달려 들어가는 침투가 없어서 상대 수비가 편하게 라인을 지킬 수 있었습니다.')
        advice.append('공이 측면이나 중원에서 풀릴 때 한 명은 수비 라인 뒤로 먼저 출발하는 침투를 약속해 두면 상대 라인이 내려앉게 됩니다.')
    change = events.get('line_change')
    if change == 'step_up':
        strengths.append('상대가 수비 라인을 끌어올리는 순간이 있었고, 그 뒤에 열린 공간이 이 장면의 기회였습니다.')
        advice.append('상대가 라인을 올릴 때는 한 박자 빠른 침투와 수비 뒤로 넘기는 패스가 가장 위험하니, 라인이 올라오는 신호를 보고 출발하는 습관을 들이세요.')
    elif change == 'drop':
        cautions.append('상대가 수비 라인을 내려 공간을 좁히며 물러섰습니다.')
    balance = events.get('balance')
    if balance:
        zone = zone_words.get(balance['zone'], '중원')
        if balance['ours'] > balance['theirs'] and balance['ours'] >= 2:
            strengths.append(f'{zone} 싸움에서 우리가 {balance["ours"]}대 {balance["theirs"]}로 숫자에서 앞섰습니다.')
        elif balance['theirs'] > balance['ours']:
            cautions.append(f'{zone} 싸움에서 우리가 {balance["ours"]}대 {balance["theirs"]}로 숫자에서 밀렸습니다.')
            advice.append(f'{zone}에서 숫자가 부족할 때는 반대편 선수가 안쪽으로 좁혀 들어오거나 공을 빠르게 돌려 숫자가 맞는 곳으로 옮겨야 합니다.')
    box = events.get('box')
    if box:
        if box['ours'] >= 3:
            strengths.append(f'마무리 단계에서 박스 안에 우리 선수가 {box["ours"]}명 들어가 있어 마무리 숫자가 충분했습니다.')
        elif box['ours'] <= 1:
            cautions.append('마무리 단계에서 박스 안에 들어간 우리 선수가 거의 없어 마무리 숫자가 부족했습니다.')
            advice.append('공이 측면에 있을 때 반대편 선수와 2선 선수가 박스 안으로 들어가는 약속이 필요합니다.')
        if box['theirs'] >= box['ours'] + 2:
            cautions.append('박스 안에서는 상대 수비 숫자가 더 많았습니다.')
    if events.get('set_piece'):
        advice.append('세트피스 상황으로 보입니다. 박스 안 선수들의 위치를 미리 정해 두고, 공이 차이기 전에 움직이기 시작하는 타이밍을 맞추면 마무리가 쉬워집니다.')
    return strengths, cautions, advice, block


def coaching_text(kind, window):
    """Korean coaching card for a scene in football words: summary, strengths, cautions, advice, a question for the players."""
    phase = PHASE_NAMES[window['phase']]
    side = SIDE_WORDS.get(window.get('side'), '')
    strengths, cautions, advice, block = analysis_sentences(window)
    where = f'{side} 쪽에서' if side else ''
    if kind == 'goal':
        opening = '세트피스 상황에서' if (window.get('events') or {}).get('set_piece') else f'{where}'.strip()
        summary = f'골이 나기 전 25초 동안 우리 팀이 {opening} 상대 진영으로 올라가 공격을 이어 갔습니다. {block}'.replace('  ', ' ')
        watch = f'골이 들어가기 전 우리 팀이 어떻게 전진하고 상대 수비가 어떻게 몰리는지 보세요. 표시된 선수의 움직임(영상의 노란 궤적과 미니맵의 하얀 궤적)을 따라가 주세요.'
        question = '이 득점 장면에서 우리가 가장 잘 만든 것은 무엇이었고, 다음에도 같은 장면을 만들려면 누가 어디에 서 있어야 할까요?'
    elif kind == 'good':
        summary = f'{where} 구조가 좋았던 장면입니다. {block}'.replace('  ', ' ')
        watch = '상대 수비 라인과 미드필드 사이에 서 있는 우리 선수들의 움직임을 보세요.'
        question = '라인 사이로 들어간 선수는 공을 받기 전에 어디를 보고 있었을까요?'
    else:
        summary = f'{where} 보완이 필요한 장면입니다. {block}'.replace('  ', ' ')
        watch = '가장 앞에 선 우리 선수와 가장 가까운 동료 사이의 거리를 보세요.'
        question = '이 장면에서 앞선 선수에게 가장 가까운 동료는 누구였고, 어디로 움직였어야 했을까요?'
    if not advice:
        advice.append('이 구조를 다른 쪽 측면에서도 같은 방식으로 반복해 보세요.' if kind != 'poor' else '앞선 선수와 중간 선수들의 간격을 줄여 서로 지원할 수 있게 해 주세요.')
    advice.append('이 분석은 선수 위치만 바탕으로 한 관찰이라 공의 흐름은 영상으로 함께 확인해 주세요.')
    return {'phase': phase, 'watch': watch, 'summary': summary, 'strengths': strengths or ['뚜렷하게 눈에 띄는 강점은 이 장면의 위치만으로는 찾기 어려웠습니다.'],
            'cautions': cautions or ['이 장면의 위치에서는 큰 약점이 보이지 않았습니다.'], 'advice': ' '.join(advice), 'question': question,
            'points': strengths + cautions}
