from app.position_slots import assign_slots


def team(depths_lateral):
    return [(f't{i}', d, y) for i, (d, y) in enumerate(depths_lateral)]


def test_a_442_team_attacking_right_gets_left_and_right_slots_from_the_team_point_of_view():
    # attacking toward +x: the right hand of the team is +y (the side of the picture nearest the camera)
    players = team([(-40, 0), (-25, -22), (-26, -8), (-26, 8), (-25, 22), (-8, -24), (-9, -8), (-9, 8), (-8, 24), (10, -6), (11, 6)])
    result = assign_slots(players, 1)
    s = result['slots']
    assert result['formation'] == '4-4-2' and result['goalkeeper'] == 't0'
    assert s['t0'] == 'GK' and s['t1'] == 'LB' and s['t4'] == 'RB' and s['t5'] == 'LM' and s['t8'] == 'RM' and s['t9'] == 'LS' and s['t10'] == 'RS'


def test_the_same_team_attacking_left_is_mirrored_so_the_hands_stay_the_team_hands():
    players = team([(40, 0), (25, 22), (26, 8), (26, -8), (25, -22), (8, 24), (9, 8), (9, -8), (8, -24), (-10, 6), (-11, -6)])
    result = assign_slots(players, -1)
    s = result['slots']
    assert result['formation'] == '4-4-2' and s['t1'] == 'LB' and s['t4'] == 'RB'      # y = +22 is the left hand when the team attacks toward -x


def test_a_lone_deep_player_is_the_goalkeeper_only_when_he_stands_well_behind_and_enough_players_are_found():
    near = team([(-30, 0), (-26, -20), (-26, -7), (-26, 7), (-25, 20), (-8, -20), (-9, 0), (-9, 20), (10, 0)])
    assert assign_slots(near, 1)['goalkeeper'] is None                    # the deepest is only 4 m behind the others
    few = assign_slots(team([(-40, 0), (-20, -10), (-18, 10), (0, 0), (10, 5)]), 1)
    assert few['goalkeeper'] is None and few['formation'] is None and set(few['slots'].values()) <= {'defence', 'midfield', 'attack'}


def test_too_few_players_give_nothing():
    assert assign_slots(team([(0, 0), (5, 5)]), 1) == {'slots': {}, 'formation': None, 'goalkeeper': None}


def test_a_shape_that_cannot_be_a_formation_falls_back_to_the_three_lines():
    # nine players stand almost in one line and one at each end: the cut would give 9-1-1
    players = team([(-30, -20), (-29, -15), (-29, -10), (-28, -5), (-28, 0), (-28, 5), (-29, 10), (-29, 15), (-30, 20), (-5, 0), (20, 0)])
    result = assign_slots(players, 1)
    assert result['formation'] is None and set(result['slots'].values()) <= {'GK', 'defence', 'midfield', 'attack'}
