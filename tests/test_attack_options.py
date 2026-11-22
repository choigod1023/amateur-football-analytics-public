from app.attack_options import analyse, segment_distance
from app.review_text import attack_story


def frame(ours, theirs):
    return {'B': [(t, u, y) for t, u, y in ours], 'A': [(t, u, y) for t, u, y in theirs]}


def test_segment_distance():
    assert segment_distance((5, 3), (0, 0), (10, 0)) == 3.0
    assert segment_distance((-4, 3), (0, 0), (10, 0)) == 5.0          # beyond the end of the segment: distance to the end point


def test_a_pass_lane_is_blocked_by_a_defender_on_the_line_and_open_otherwise():
    ours = [('1', 20.0, 10.0), ('2', 30.0, 10.0), ('3', 20.0, -10.0), ('4', 5.0, 8.0), ('5', 10.0, 0.0)]
    theirs = [('a', 25.0, 10.5), ('b', 20.0, 0.0), ('c', 30.0, -8.0), ('d', 2.0, 20.0)]
    by_frame = {f: frame(ours, theirs) for f in range(0, 200)}
    facts = analyse(by_frame, 'B', 'A', 1, 5.0, 0.0, 20.0, carrier='1')
    lanes = {l['track']: l for l in facts['lanes']}
    assert facts['carrier'] == '1' and facts['carrier_source'] == 'given'
    assert not lanes['2']['open'] and lanes['2']['blocker'] == 'a'           # the defender stands on the line to the player ahead
    assert not lanes['3']['open'] and lanes['3']['blocker'] == 'b' and lanes['3']['across']
    assert lanes['4']['open'] and not lanes['4']['forward']


def test_without_a_given_carrier_the_most_advanced_player_is_used_and_said_so():
    ours = [('1', 30.0, 20.0), ('2', 20.0, 18.0), ('3', 15.0, 5.0), ('4', 18.0, -22.0), ('5', 5.0, 0.0)]
    theirs = [('a', 34.0, 18.0), ('b', 28.0, 16.0), ('c', 30.0, 2.0), ('d', 12.0, 8.0), ('e', 10.0, -2.0)]
    by_frame = {f: frame(ours, theirs) for f in range(0, 200)}
    facts = analyse(by_frame, 'B', 'A', 1, 5.0, 0.0, 20.0)
    assert facts['carrier'] == '1' and facts['carrier_source'] == 'most advanced' and facts['side'] == 'near'


def test_allowed_removes_players_of_the_other_team_who_carry_our_label():
    ours = [('1', 30.0, 0.0), ('2', 20.0, 5.0), ('3', 15.0, -5.0), ('4', 10.0, 10.0), ('5', 12.0, -9.0)]
    theirs = [('a', 33.0, 1.0), ('b', 25.0, 2.0), ('c', 12.0, 0.0), ('d', 5.0, 3.0)]
    by_frame = {f: frame(ours, theirs) for f in range(0, 100)}
    assert analyse(by_frame, 'B', 'A', 1, 5.0, 0.0, 10.0, allowed={'2', '3', '4', '5'})['carrier'] == '2'      # '1' wears the other shirt
    assert analyse(by_frame, 'B', 'A', 1, 5.0, 0.0, 10.0, allowed={'2', '3'}) is None                        # fewer than four players left


def test_too_few_players_give_no_analysis():
    by_frame = {f: frame([('1', 30.0, 0.0), ('2', 10.0, 3.0)], [('a', 5.0, 0.0)]) for f in range(0, 50)}
    assert analyse(by_frame, 'B', 'A', 1, 5.0, 0.0, 5.0) is None


def test_the_story_talks_about_lanes_and_never_tells_a_scorer_to_hurry():
    lanes = [{'track': '3', 'u': 20.0, 'y': -10.0, 'length': 25.0, 'clear': 6.0, 'open': True, 'blocker': None, 'forward': True, 'across': True},
             {'track': '2', 'u': 30.0, 'y': 10.0, 'length': 10.0, 'clear': 0.5, 'open': False, 'blocker': 'a', 'forward': True, 'across': False}]
    facts = {'side': 'near', 'lanes': lanes, 'shift': 3.0, 'width': 30.0, 'goal_side': 4, 'ours': 8, 'theirs': 8, 'carrier_source': 'given'}
    missed = attack_story(facts, to_goal=False)
    text = ' '.join(missed['good'] + missed['fix'] + [missed['next']])
    assert '패스길' in text and '막' in text and '반대편' in text and '골 직후' not in text and '빨리 올' not in text
    assert len(missed['fix']) >= 2
    scored = attack_story({**facts, 'shift': 15.0}, to_goal=True)
    assert len(scored['fix']) <= 1 and any('방향' in line or '전환' in line for line in scored['good'])


def test_describe_gives_the_path_the_defence_and_the_empty_lane_in_words():
    from app.attack_options import describe
    ours = [('1', 5.0, 25.0), ('2', 10.0, 10.0), ('3', 0.0, 0.0), ('4', -10.0, -5.0), ('5', 8.0, -20.0)]
    theirs = [('a', 36.0, -4.0), ('b', 35.0, 4.0), ('c', 37.0, 12.0), ('d', 34.0, 20.0), ('g', 44.0, 0.0), ('m', 15.0, 10.0)]
    by_frame = {}
    for f in range(0, 400):
        lead_u = min(33.0, 35.0 - (60.0 - f / 5.0) * 3.0)
        by_frame[f] = {'B': [('1', lead_u, 25.0)] + [(t, u, y) for t, u, y in ours[1:]], 'A': theirs}
    facts = analyse(by_frame, 'B', 'A', 1, 5.0, 0.0, 60.0)
    words = describe(by_frame, 'B', 'A', 1, 5.0, 0.0, 60.0, facts)
    text = ' '.join(words['scene'] + words['space'])
    assert '가까운 쪽 측면' in words['path'] and '순서로' in ' '.join(words['scene'])
    assert '수비 4명' in text and '골라인까지' in text
    assert '구역에는 상대 수비수가 없었' in text
