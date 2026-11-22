from app.report_scenes import coaching_text, key_player, phase_of, pick_windows, second_metrics, window_scores


def team(xs, base=0):
    return [(base + i, x, (i % 4) * 12 - 18) for i, x in enumerate(xs)]


def test_metrics_need_enough_players_and_measure_between_the_lines():
    mine = team([-40, -15, -15, -15, -15, 5, 5, 5, 20, 22, 30])
    theirs = team([40, 20, 20, 20, 20, 0, 0, 0, -15, -15, -15], base=100)       # their back line stands at u = 20
    assert second_metrics(mine[:5], theirs) is None
    m = second_metrics(mine, theirs, direction=1)
    assert m['opponent_back_line'] > 10 and m['leader'] == 10 and m['ahead'] >= 4
    assert second_metrics(team([40, 20, 20, 20, 20, 0, 0, 0, -15, -15, -15]), team([-40, -15, -15, -15, -15, 5, 5, 5, 20, 22, 30], base=100), direction=-1)['leader'] in (8, 9, 10)


def test_phase_follows_the_thirds_and_windows_choose_apart_from_each_other():
    assert (phase_of(-20), phase_of(0), phase_of(20)) == ('build_up', 'progression', 'final_third')
    base = {'centre': 10.0, 'ahead': 6, 'forward_lanes': 3, 'line_breaking': 0, 'between': [], 'attack_line': 20.0, 'middle_line': 5.0, 'defence_line': -10.0,
            'opponent_back_line': 25.0, 'gap_mid_attack': 25.0, 'leader': 7, 'leader_isolation': 30.0, 'width': 40.0, 'lane_pairs': []}
    series = {s: dict(base) for s in range(0, 100)}
    for s in range(60, 80):
        series[s] = {**base, 'line_breaking': 3, 'between': [4, 5], 'forward_lanes': 15, 'leader_isolation': 6.0, 'attack_line': 30.0}
    scores = window_scores(series, 15)
    good = pick_windows(scores, 'good', count=2, spacing=40)
    assert good and 55 <= good[0]['start'] <= 70
    poor = pick_windows(scores, 'poor', count=3, spacing=40)
    assert poor and all(w['start'] < 55 or w['start'] > 75 for w in poor) and len(poor) <= 3
    assert key_player(series, good[0], 'good') in (4, 5) and key_player(series, poor[0], 'poor') == 7


def test_coaching_text_speaks_in_football_words_and_names_the_side():
    window = {'phase': 'progression', 'side': 'near', 'means': {'opponent_back_line': 34.0, 'between': 2.5, 'line_breaking': 1.8, 'attack_line': 36.0, 'leader_isolation': 20.0, 'forward_lanes': 4.0,
                                                           'gap_mid_attack': 28.0, 'centre': 14.0, 'width': 41.0}}
    good, poor = coaching_text('good', window), coaching_text('poor', window)
    goal = coaching_text('goal', window)
    assert '낮은 블록' in goal['summary'] and '가까운 쪽 측면' in goal['summary']
    assert any('미드필더와 수비수 사이' in s for s in goal['strengths']) and any('혼자 싸우는' in c for c in goal['cautions'])
    assert '지원 각도' in goal['advice'] and goal['question'].endswith('?')
    assert not any(ch.isdigit() for ch in ' '.join(goal['strengths'] + goal['cautions']))        # no numbers in the football wording
    low = {**window, 'means': {**window['means'], 'opponent_back_line': 8.0, 'between': 0.0, 'line_breaking': 0.0, 'attack_line': 0.0, 'centre': -3.0, 'width': 20.0, 'leader_isolation': 5.0}}
    text = coaching_text('poor', low)
    assert '높이 올려' in text['summary'] and any('우리 진영' in c for c in text['cautions']) and '두 방향' in text['advice']
