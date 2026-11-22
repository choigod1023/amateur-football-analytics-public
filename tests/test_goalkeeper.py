from app.goalkeeper import goalkeeper_depth_is_keeper, without_goalkeeper


def depths(*values):
    return sorted(values)


def test_a_deepest_player_far_from_the_goal_line_is_a_defender():
    assert goalkeeper_depth_is_keeper(depths(-25, -23, -20, -10, -5, 0, 5, 10, 15, 20)) is False


def test_a_goalkeeper_close_behind_a_deep_defence_is_cut():
    assert goalkeeper_depth_is_keeper(depths(-42, -36, -35, -34, -33, -20, -15, -10, 0, 10, 20)) is True


def test_a_player_next_to_the_goal_line_is_the_goalkeeper_even_with_a_small_gap():
    assert goalkeeper_depth_is_keeper(depths(-42, -41, -40, -38, -30, -20, -10, 0, 10, 20)) is True


def test_too_few_players_cuts_nobody():
    assert without_goalkeeper([(-42, 0), (-30, 0), (-10, 0)])[1] is False
