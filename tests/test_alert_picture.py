import json

from app import alert_picture as ap
from app.bench_view import BenchView


def write_positions(path, seconds, direction=1, half=None):
    """seconds: [(time, team [(id, x, y)], other [(id, x, y)])] in screen metres."""
    lines = [{'type': 'header', 'team': 'B', 'other': 'A', 'direction': direction, 'pitch_length': 89.0, 'pitch_width': 62.0, 'first_second': 0.0}]
    if half:
        lines.append({'type': 'half', 'half': 2, 'direction': half[1], 'time': half[0]})
    for t, team, other in seconds:
        lines.append({'type': 'second', 'time': t, 'team': [list(p) for p in team], 'other': [list(p) for p in other]})
    path.write_text('\n'.join(json.dumps(l) for l in lines) + '\n', encoding='utf-8')


def sinking_line(direction=1):
    """Our back three stand at u = -10 at 0..4 s and at -26 from 8 s on (team view); midfield and attack stay. Screen x = u * direction, y = v * direction."""
    out = []
    for t in range(0, 13):
        back = -10.0 if t < 8 else -26.0
        team = [(1, back, -12.0), (2, back, 0.0), (3, back, 12.0), (4, 5.0, -10.0), (5, 5.0, 10.0), (6, 20.0, 0.0), (7, -42.0, 0.0)]   # 7: the goalkeeper
        out.append((float(t), [(k, u * direction, v * direction) for k, u, v in team], [(20 + k, (u + 15) * direction, v * direction) for k, u, v in team[:5]]))
    return out


def drop_row(t=12.0, supported=True):
    return {'time': t, 'kind': 'line_drop', 'title': '수비 라인 하락', 'text': 'x', 'polarity': 'poor',
            'evidence': {'drop': 16, 'retreat_supported': supported}, 'directive': {'status': 'conditional' if supported else 'review_required'}}


def segment(tmp_path, seconds, direction=1, half=None):
    path = tmp_path / 'positions.jsonl'
    write_positions(path, seconds, direction, half)
    return ap.read_segments(path)[-1]


def test_line_drop_draws_the_back_line_and_arrows_up_to_the_earlier_line(tmp_path):
    pic = ap.picture(drop_row(), segment(tmp_path, sinking_line()))
    assert pic and pic['line'] == '수비 줄을 함께 올리세요'
    lines = {l['style']: l['u'] for l in pic['lines']}
    assert lines['now'] == -26.0 and lines['before'] == -10.0
    assert sorted(f[1] for f in pic['focus']) == [-12.0, 0.0, 12.0]                 # the three defenders, not the goalkeeper
    assert len(pic['arrows']) == 3 and all(a['style'] == 'dashed' and a['to'][0] > a['from'][0] and a['to'][1] == a['from'][1] for a in pic['arrows'])


def test_direction_minus_one_gives_the_same_team_view(tmp_path):
    plus = ap.picture(drop_row(), segment(tmp_path, sinking_line(1), 1))
    minus = ap.picture(drop_row(), segment(tmp_path, sinking_line(-1), -1))
    assert plus['lines'] == minus['lines'] and sorted(map(tuple, plus['focus'])) == sorted(map(tuple, minus['focus']))
    assert plus['arrows'] == minus['arrows'] and minus['direction'] == -1


def test_a_half_row_changes_the_direction_from_its_time(tmp_path):
    seconds = [(t + 100.0, team, other) for t, team, other in sinking_line(-1)]
    seg = segment(tmp_path, seconds, direction=1, half=(50.0, -1))
    pic = ap.picture(drop_row(112.0), seg)
    assert pic and pic['direction'] == -1 and {l['style']: l['u'] for l in pic['lines']}['now'] == -26.0


def test_unconfirmed_drop_and_unknown_kinds_give_only_a_short_line(tmp_path):
    seg = segment(tmp_path, sinking_line())
    held = ap.picture(drop_row(supported=False), seg)
    assert held['type'] == 'position' and held['arrows'] == []             # no arrow picture without the retreat evidence: the position map, a line only
    assert ap.short_line(drop_row(supported=False)) == '수비선 확인 필요'
    odd = {'time': 12.0, 'kind': 'something_new', 'title': '아주 긴 새 알림 제목이 여기에 들어갑니다', 'polarity': 'poor'}
    assert ap.picture(odd, seg) is None and len(ap.short_line(odd)) <= 15
    assert ap.picture({'time': 12.0, 'kind': 'no_input', 'polarity': 'status'}, seg) is None


def test_too_few_of_our_points_or_no_row_near_the_moment_gives_no_picture(tmp_path):
    few = [(t, team[:3], other) for t, team, other in sinking_line()]
    assert ap.picture(drop_row(), segment(tmp_path, few)) is None
    assert ap.picture(drop_row(t=40.0), segment(tmp_path, sinking_line())) is None


def test_every_short_line_is_at_most_15_characters():
    assert all(len(v) <= 15 for v in ap.LINES.values())


def test_kinds_turned_back_to_text_get_no_arrow_picture_but_their_rules_still_compute(tmp_path):
    """conceded_run, box_attack and run failed (or could not be checked in) the video check of 2026-11-24: picture() gives no ARROW picture for them (a position map instead)."""
    seconds = []
    for t in range(0, 8):
        team = [(1, -20.0, -10.0), (2, -20.0, 0.0), (3, -20.0, 10.0), (4, 0.0, 0.0), (5, 10.0, 5.0)]
        other = [(31, 10.0 - 4.0 * t, 20.0)]                                             # runs from u 10 to u -18, past our line at -20 + 2
        seconds.append((float(t), team, other))
    seg = segment(tmp_path, seconds)
    row = {'time': 7.0, 'kind': 'conceded_run', 'polarity': 'poor'}
    shown = ap.picture(row, seg)
    assert shown['type'] == 'position' and shown['arrows'] == [] and shown['threat'] == []
    pic = ap.RULES['conceded_run'](row, seg, 7.0, 1)
    assert pic['threat'] == [[-18.0, 20.0]] and pic['arrows'][0]['side'] == 'theirs' and pic['arrows'][0]['to'][0] < pic['arrows'][0]['from'][0]
    no_opponents = segment(tmp_path, [(t, team, []) for t, team, _ in seconds])
    assert ap.RULES['conceded_run'](row, no_opponents, 7.0, 1) is None


def test_box_attack_rule_sends_at_most_three_players_to_the_posts_and_the_back(tmp_path):
    team = [(1, 32.0, -2.0), (2, 33.0, 0.0), (3, 34.0, 2.0), (4, 30.0, 1.0), (5, 0.0, 0.0)]
    seg = segment(tmp_path, [(float(t), team, []) for t in range(0, 4)])
    pic = ap.RULES['box_attack']({'time': 3.0, 'kind': 'box_attack', 'evidence': {'width': 4, 'depth': 4}}, seg, 3.0, 1)
    assert len(pic['focus']) == 4 and 1 <= len(pic['arrows']) <= 3 and all(a['style'] == 'dashed' for a in pic['arrows'])
    spread = ap.RULES['box_attack']({'time': 3.0, 'kind': 'box_attack', 'evidence': {'width': 14, 'depth': 9}}, seg, 3.0, 1)
    assert spread['arrows'] == [] and spread['line'] == '박스 안 자리 지키기'


def test_bench_snapshot_carries_the_line_and_the_picture(tmp_path):
    folder = tmp_path / 'alerts' / 'live1'
    folder.mkdir(parents=True)
    write_positions(folder / 'positions.jsonl', sinking_line())
    rows = [{'time': 5.0, 'kind': 'heartbeat', 'type': 'heartbeat', 'polarity': 'status'}, drop_row()]
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    snap = BenchView(tmp_path).snapshot()
    current = snap['current']
    assert current['line'] == '수비 줄을 함께 올리세요' and current['title'] == '수비 라인 하락' and current['text'] == 'x'
    assert current['picture']['lines'] and len(current['picture']['arrows']) == 3 and current['picture']['type'] == 'arrows'


def test_live_rows_of_the_1124_rehearsal_in_writing_order(tmp_path):
    """Shaped on the 2026-11-24 rehearsal (11-20 video streamed live): line_drop #23 (retreat_supported, directive conditional) and #142
    (retreat_supported false, directive review_required, title '수비선 관측 변동'). The positions file holds only the seconds written up to the alert,
    as the live run writes the position line of a frame before its alerts. #23 gets the picture at once; #142 gets none by design (text only)."""
    folder = tmp_path / 'alerts' / 'rehearsal-20261124'
    folder.mkdir(parents=True)
    seconds = [(t + 104.0, team, other) for t, team, other in sinking_line(-1)]          # 104 .. 116 s, team B attacks left (direction -1)
    write_positions(folder / 'positions.jsonl', seconds, direction=-1)
    evidence = {'basis': 'player_positions', 'ball_observed': False, 'drop': 15, 'retreat_supported': True, 'shared_tracks': 3, 'median_retreat_m': 12.0, 'comparison_seconds': 10}
    supported = {'time': 115.9, 'kind': 'line_drop', 'polarity': 'poor', 'title': '수비 라인 하락', 'text': 'x', 'confidence': 'reference', 'latency_ms': 95,
                 'evidence': evidence, 'directive': {'target': {'scope': 'group', 'track_ids': []}, 'status': 'conditional', 'individual_assignment_verified': False}}
    heartbeat = {'time': 114.9, 'kind': 'heartbeat', 'type': 'heartbeat', 'polarity': 'status', 'wall': 1795529445.6}
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in (heartbeat, supported)) + '\n', encoding='utf-8')
    current = BenchView(tmp_path).snapshot()['current']
    assert current['number'] == 1 and current['line'] == '수비 줄을 함께 올리세요'
    assert current['picture'] and current['picture']['direction'] == -1 and len(current['picture']['arrows']) == 3
    held = {**supported, 'time': 703.9, 'polarity': 'info', 'title': '수비선 관측 변동',
            'evidence': {**evidence, 'drop': 14, 'retreat_supported': False, 'median_retreat_m': 6.68, 'comparison_seconds': 4},
            'directive': {'target': {'scope': 'staff', 'track_ids': []}, 'status': 'review_required', 'individual_assignment_verified': False}}
    write_positions(folder / 'positions.jsonl', seconds + [(t + 692.0, team, other) for t, team, other in sinking_line(-1)], direction=-1)
    with open(folder / 'alerts.jsonl', 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(held, ensure_ascii=False) + '\n')
    current = BenchView(tmp_path).snapshot()['current']
    assert current['number'] == 2 and current['picture']['type'] == 'position' and current['picture']['arrows'] == [] and current['line'] == '수비선 확인 필요'


def test_bench_snapshot_without_positions_still_works(tmp_path):
    folder = tmp_path / 'alerts' / 'live1'
    folder.mkdir(parents=True)
    (folder / 'alerts.jsonl').write_text(json.dumps(drop_row(), ensure_ascii=False) + '\n', encoding='utf-8')
    current = BenchView(tmp_path).snapshot()['current']
    assert current['picture'] is None and current['line'] == '수비 줄을 함께 올리세요'


# ---- the position map (2026-11-25) --------------------------------------------------------------------------------------------------
def defence_seconds(opponent_at, direction=1, t_end=6):
    """Our back three at u = -20, midfield and attack ahead, the keeper at -42; one opponent per second at `opponent_at(t)` = (u, v)."""
    out = []
    for t in range(0, t_end + 1):
        team = [(1, -20.0, -10.0), (2, -20.0, 0.0), (3, -20.0, 10.0), (4, 0.0, 0.0), (5, 10.0, 5.0), (7, -42.0, 0.0)]
        other = [(31, *opponent_at(t)), (32, 15.0, -8.0)]
        out.append((float(t), [(k, u * direction, v * direction) for k, u, v in team], [(k, u * direction, v * direction) for k, u, v in other]))
    return out


def test_conceded_run_map_fills_the_space_behind_our_line_and_rings_the_opponent_inside(tmp_path):
    seg = segment(tmp_path, defence_seconds(lambda t: (-10.0, 20.0)))
    pic = ap.picture({'time': 6.0, 'kind': 'conceded_run', 'polarity': 'poor'}, seg)
    assert pic['type'] == 'position' and pic['arrows'] == [] and pic['threat'] == []
    zone = pic['zones'][0]
    assert zone['u0'] == -44.5 and zone['u1'] == -20.0 and zone['v0'] == -31.0 and zone['v1'] == 31.0
    assert pic['focus'] == []                                                       # the opponent at u -10 is still in front of the line at -20
    assert pic['lines'] == [{'u': -20.0, 'style': 'back'}] and len(pic['ours']) == 6 and len(pic['theirs']) == 2
    seg2 = segment(tmp_path, defence_seconds(lambda t: (-30.0, 20.0)))
    inside = ap.picture({'time': 6.0, 'kind': 'conceded_run', 'polarity': 'poor'}, seg2)
    assert inside['focus'] == [[-30.0, 20.0]] and inside['legend'] == ap.CAPTIONS['behind']


def test_box_attack_map_fills_the_attacked_box_and_rings_every_point_inside(tmp_path):
    team = [(1, 32.0, -2.0), (2, 33.0, 0.0), (3, 34.0, 2.0), (4, 0.0, 0.0), (5, -20.0, 0.0)]
    other = [(31, 35.0, 5.0), (32, 10.0, 0.0)]
    seg = segment(tmp_path, [(float(t), team, other) for t in range(0, 4)])
    pic = ap.picture({'time': 3.0, 'kind': 'box_attack', 'polarity': 'info', 'evidence': {'width': 4, 'depth': 4}}, seg)
    assert pic['type'] == 'position' and pic['arrows'] == [] and pic['zones'] == [{'u0': 28.0, 'u1': 44.5, 'v0': -20.16, 'v1': 20.16}]
    assert len(pic['focus']) == 4                                                   # three of ours and the opponent at u 35


def test_other_kinds_and_unsupported_line_drop_get_the_back_line_only(tmp_path):
    seg = segment(tmp_path, defence_seconds(lambda t: (0.0, 0.0)))
    for kind in ('gap_wide', 'isolated', 'run', 'line_drop'):
        pic = ap.picture({'time': 6.0, 'kind': kind, 'polarity': 'info'}, seg)
        assert pic and pic['type'] == 'position' and pic['zones'] == [] and pic['focus'] == [] and pic['lines'] == [{'u': -20.0, 'style': 'back'}], kind


def test_direction_minus_one_gives_the_same_position_map(tmp_path):
    plus = ap.picture({'time': 6.0, 'kind': 'conceded_run'}, segment(tmp_path, defence_seconds(lambda t: (-30.0, 20.0), 1), 1))
    minus = ap.picture({'time': 6.0, 'kind': 'conceded_run'}, segment(tmp_path, defence_seconds(lambda t: (-30.0, 20.0), -1), -1))
    assert plus['zones'] == minus['zones'] and plus['focus'] == minus['focus'] and plus['lines'] == minus['lines'] and minus['direction'] == -1


def test_position_map_never_uses_a_row_after_the_alert(tmp_path):
    # the opponent stands behind our line only from 7 s on; the alert is at 5.5 s and the file already holds rows up to 8 s
    seconds = defence_seconds(lambda t: (-30.0, 20.0) if t >= 7 else (-5.0, 20.0), t_end=8)
    seg = segment(tmp_path, seconds)
    pic = ap.picture({'time': 5.5, 'kind': 'conceded_run'}, seg)
    assert pic['time'] == 5.0 and pic['focus'] == []
    assert ap.picture({'time': 7.2, 'kind': 'conceded_run'}, seg)['focus'] == [[-30.0, 20.0]]
    only_later = [(t, a, b) for t, a, b in seconds if t >= 6.0]
    assert ap.picture_with_reason({'time': 5.5, 'kind': 'conceded_run'}, segment(tmp_path, only_later)) == (None, 'no_position_row')


def test_position_map_conditions_that_give_no_picture(tmp_path):
    seg = segment(tmp_path, defence_seconds(lambda t: (-30.0, 20.0)))
    assert ap.picture_with_reason({'time': 40.0, 'kind': 'conceded_run'}, seg) == (None, 'no_position_row')           # the last row is more than 2 s before
    few = [(t, team[:3], other) for t, team, other in defence_seconds(lambda t: (-30.0, 20.0))]
    assert ap.picture_with_reason({'time': 6.0, 'kind': 'box_attack'}, segment(tmp_path, few)) == (None, 'few_ours')
    assert ap.picture_with_reason({'time': 6.0, 'kind': 'half_switch'}, seg) == (None, 'other_kind')
    assert ap.picture_with_reason({'time': 6.0, 'kind': 'no_input', 'polarity': 'status'}, seg) == (None, 'status')
    assert ap.picture_with_reason({'time': 6.0, 'kind': 'conceded_run'}, None) == (None, 'no_record')


def test_arrow_picture_of_a_supported_line_drop_is_unchanged_except_for_its_type(tmp_path):
    pic = ap.picture(drop_row(), segment(tmp_path, sinking_line()))
    assert pic['type'] == 'arrows' and pic['zones'] == [] and pic['focus'] and len(pic['arrows']) == 3
    assert [a['style'] for a in pic['arrows']] == ['dashed'] * 3 and {l['style'] for l in pic['lines']} == {'before', 'now'}
    assert 'legend' not in pic


def test_bench_snapshot_carries_the_position_map_for_a_conceded_run(tmp_path):
    folder = tmp_path / 'alerts' / 'live1'
    folder.mkdir(parents=True)
    write_positions(folder / 'positions.jsonl', defence_seconds(lambda t: (-30.0, 20.0)))
    row = {'time': 6.0, 'kind': 'conceded_run', 'title': '상대 침투 허용', 'text': 'x', 'polarity': 'poor'}
    (folder / 'alerts.jsonl').write_text(json.dumps(row, ensure_ascii=False) + '\n', encoding='utf-8')
    current = BenchView(tmp_path).snapshot()['current']
    assert current['picture']['type'] == 'position' and current['title'] == '상대 침투 허용' and current['line'] == '가까운 수비 따라붙기'
