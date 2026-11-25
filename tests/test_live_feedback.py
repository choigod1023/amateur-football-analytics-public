from app.live_feedback import LiveAnalyzer


def squad(x_front, count=10, shift=0.0):
    """Ten outfield players of one team spread over four lines, toward +x."""
    xs = [x_front, x_front - 4, x_front - 8, x_front - 12, x_front - 16, x_front - 20, x_front - 24, x_front - 28, x_front - 32, x_front - 36][:count]
    return [(i + 1, x + shift, ((i * 11) % 40) - 20) for i, x in enumerate(xs)]


def play(analyzer, seconds, make):
    alerts = []
    for step in range(int(seconds * analyzer.fps)):
        t = step / analyzer.fps
        team, other = make(t)
        alerts += analyzer.update(t, team, other)
    return alerts


def test_three_players_in_the_box_for_two_seconds_raise_one_alert_then_stay_quiet_for_the_cooldown():
    analyzer = LiveAnalyzer(direction=1, fps=5.0, cooldown=25.0)
    box = [(21, 40.0, -5.0), (22, 38.0, 2.0), (23, 37.0, 8.0)]

    def make(t):
        team = squad(30.0) + (box if t >= 3 else [])
        other = [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(30.0))]
        return team, other
    alerts = play(analyzer, 12, make)
    boxes = [a for a in alerts if a['kind'] == 'box_attack']
    assert len(boxes) == 1 and 4.0 <= boxes[0]['time'] <= 7.0
    # Position counts establish occupancy, not a successful attacking action.
    assert '박스 안에' in boxes[0]['text'] and boxes[0]['polarity'] == 'info' and boxes[0]['rules']
    assert boxes[0]['title'] == '박스 안 선수 배치'


def test_a_lone_front_player_is_reported_after_six_seconds():
    analyzer = LiveAnalyzer(direction=1, fps=5.0, disabled=())      # isolated is off by default since 2026-11-20 (DISABLED_KINDS); the rule itself is tested here

    def make(t):
        team = [(1, 30.0, 0.0), (11, -42.0, 0.0)] + [(i + 2, 15.0 - 2 * i, (i * 7) % 30 - 15) for i in range(9)]
        other = [(100 + i, 30.0 - 4 * i, (i * 5) % 30 - 15) for i in range(10)] + [(200, 42.0, 0.0)]
        return team, other
    alerts = play(analyzer, 12, make)
    assert [a['kind'] for a in alerts].count('isolated') == 1


def test_nothing_is_reported_for_a_quiet_balanced_game_and_old_samples_are_dropped():
    analyzer = LiveAnalyzer(direction=1, fps=5.0, history=10.0)

    def make(t):
        return squad(5.0), [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(5.0))]
    alerts = play(analyzer, 40, make)
    assert alerts == []
    assert all(path[0][0] >= analyzer.last_sample - 10 * analyzer.fps for side in analyzer.paths.values() for path in side.values())


def test_a_sample_that_does_not_move_time_forward_is_ignored():
    analyzer = LiveAnalyzer(direction=1, fps=5.0)
    assert analyzer.update(1.0, [], []) == [] and analyzer.update(1.0, [], []) == [] and analyzer.update(0.5, [], []) == []


def test_an_attack_alert_carries_the_passing_lanes_and_the_space_of_that_moment():
    analyzer = LiveAnalyzer(direction=1, fps=5.0, cooldown=25.0)
    box = [(21, 40.0, -5.0), (22, 38.0, 2.0), (23, 37.0, 8.0)]

    def make(t):
        team = squad(30.0) + (box if t >= 3 else [])
        other = [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(30.0))] + [(200 + i, 35.0 - 2 * i, -15 + 7 * i) for i in range(4)]
        return team, other
    alerts = play(analyzer, 12, make)
    boxes = [a for a in alerts if a['kind'] == 'box_attack']
    assert boxes and boxes[0]['detail'] is not None
    detail = boxes[0]['detail']
    assert '패스길' in detail['line'] and detail['lanes'] and detail['advice']
    assert all(a['detail'] is None for a in alerts if a['kind'] in ('conceded_run', 'line_drop', 'gap_wide'))


def test_a_player_missed_in_the_last_frame_is_still_counted_and_a_double_track_is_not():
    analyzer = LiveAnalyzer(direction=1, fps=5.0)
    analyzer.update(0.0, [(1, 0.0, 0.0), (2, 10.0, 5.0), (3, 20.0, -5.0)], [(9, -30.0, 0.0)])
    analyzer.update(0.2, [(1, 0.2, 0.0), (2, 10.2, 5.0), (4, 20.3, -5.0)], [(9, -30.0, 0.0)])        # 3 is lost, 4 appears at the same place
    analyzer.update(0.4, [(1, 0.4, 0.0)], [])
    held = analyzer.held('team', 2)
    assert sorted(t for t, _x, _y in held) == [1, 2, 4]
    assert len(analyzer.held('other', 2)) == 1


def wide_squad(wide):
    """Ten outfield players: three at the back, four in midfield, three in front; `wide` pulls the front line 45 m away from the back line."""
    back = [(i + 1, -20.0 + 2 * i, (i * 9) % 30 - 15) for i in range(3)]
    middle = [(i + 4, -5.0 + 2 * i, (i * 7) % 30 - 15) for i in range(4)]
    front = [(i + 8, (25.0 if wide else -2.0) + 2 * i, (i * 11) % 30 - 15) for i in range(3)]
    return back + middle + front


def test_a_state_alert_is_said_once_while_the_state_lasts_and_again_when_it_comes_back():
    analyzer = LiveAnalyzer(direction=1, fps=5.0, disabled=())

    def make(t):
        wide = t < 130 or t >= 180                                              # wide, compact for 50 s (longer than RELEASE), wide again
        return wide_squad(wide) + [(30, -42.0, 0.0)], [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(5.0))]
    alerts = play(analyzer, 300, make)
    gaps = [a['time'] for a in alerts if a['kind'] == 'gap_wide']
    assert len(gaps) == 2, gaps                                                 # one per episode, not one per 90 s
    assert gaps[0] < 20 and gaps[1] > 180


def test_a_state_alert_that_was_held_back_by_the_spacing_comes_later_in_the_same_episode():
    analyzer = LiveAnalyzer(direction=1, fps=5.0, disabled=())
    analyzer.last_any = 0.0                                                     # another alert was sent just now: MIN_SPACING holds the state alert back at first

    def make(t):
        return wide_squad(True) + [(30, -42.0, 0.0)], [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(5.0))]
    alerts = play(analyzer, 40, make)
    assert len([a for a in alerts if a['kind'] == 'gap_wide']) == 1


def test_an_alert_carries_a_confidence_level_and_its_evidence_and_keeps_the_old_fields():
    analyzer = LiveAnalyzer(direction=1, fps=5.0, cooldown=25.0)
    box = [(21, 40.0, -5.0), (22, 38.0, 2.0), (23, 37.0, 8.0)]

    def make(t):
        return squad(30.0) + (box if t >= 3 else []), [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(30.0))]
    alert = next(a for a in play(analyzer, 12, make) if a['kind'] == 'box_attack')
    assert alert['confidence'] == 'high' and '맞음' in alert['evidence_note']           # the judged record in words; 'evidence' holds the measured facts (main branch)
    assert alert['evidence']['basis'] == 'player_positions' and alert['evidence']['n'] >= 3
    assert {'time', 'kind', 'polarity', 'title', 'text', 'rules', 'drill', 'detail'} <= set(alert)


def test_the_box_alert_keeps_the_places_when_the_players_already_stand_spread():
    from app.live_feedback import LiveAnalyzer as Analyzer
    spread = Analyzer.message('box_attack', {'n': 4, 'width': 13, 'depth': 9})
    close = Analyzer.message('box_attack', {'n': 3, 'width': 6, 'depth': 4})
    unknown = Analyzer.message('box_attack', {'n': 3})
    assert '이미 나눠 서 있습니다' in spread and '13미터' in spread
    assert '나눠 서세요' in close and '나눠 서세요' in unknown


def test_state_alerts_carry_their_numbers_and_the_goalkeeper_note():
    from app.live_feedback import LiveAnalyzer as Analyzer
    assert '34미터' in Analyzer.message('gap_wide', {'gap': 34}) and '골키퍼 제외' in Analyzer.message('gap_wide', {'gap': 34})
    assert '15미터' in Analyzer.message('line_drop', {'drop': 15})
    assert Analyzer.message('run', {}) and '선수' in Analyzer.message('isolated', {})


def test_the_scene_words_are_put_into_the_present_tense_for_a_live_alert():
    from app.live_feedback import present_tense
    assert present_tense('상대 수비 라인 뒤에서 골라인까지 약 19미터 비어 있어 뒤로 넘기는 패스가 가능했습니다') == '상대 수비 라인 뒤에서 골라인까지 약 19미터 비어 있어 뒤로 넘기는 패스가 가능합니다'
    assert present_tense('골라인까지 약 11미터라 뒤 공간이 좁았습니다') == '골라인까지 약 11미터라 뒤 공간이 좁습니다'
    assert present_tense('문구 그대로') == '문구 그대로'


def test_the_passing_lane_line_is_one_present_tense_sentence_with_the_counts():
    analyzer = LiveAnalyzer(direction=1, fps=5.0, cooldown=25.0)
    box = [(21, 40.0, -5.0), (22, 38.0, 2.0), (23, 37.0, 8.0)]

    def make(t):
        return squad(30.0) + (box if t >= 3 else []), [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(30.0))]
    alert = next(a for a in play(analyzer, 12, make) if a['kind'] == 'box_attack')
    line = alert['detail']['line']
    assert '패스길' in line and '곳 중' in line and '열림' in line
    assert '했습니다' not in line and '았습니다' not in line


def test_gap_wide_is_off_by_default_and_can_be_turned_on():
    def make(t):
        return wide_squad(True) + [(30, -42.0, 0.0)], [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(5.0))]
    assert not [a for a in play(LiveAnalyzer(direction=1, fps=5.0), 40, make) if a['kind'] == 'gap_wide']
    assert [a for a in play(LiveAnalyzer(direction=1, fps=5.0, disabled=()), 40, make) if a['kind'] == 'gap_wide']


def test_a_dip_of_one_second_in_the_box_count_stops_a_box_alert_unless_the_tolerant_option_is_on():
    def kinds(analyzer):
        analyzer.box_seconds = {4: 3, 5: 2, 6: 3}
        return [a['kind'] for a in analyzer._check(7.0, 6)]
    assert 'box_attack' not in kinds(LiveAnalyzer(direction=1, fps=5.0))
    assert 'box_attack' in kinds(LiveAnalyzer(direction=1, fps=5.0, tolerant_box=True))
