from app.tactical_concepts import box_presence, line_change, local_balance, runs_in_behind, standing_still, zone_of


def test_a_fast_run_past_the_back_line_is_a_run_in_behind_but_a_jog_or_a_run_that_stops_short_is_not():
    back = {s: 20.0 for s in range(0, 30)}
    fast = [(f, 10.0 + 0.9 * f, 5.0) for f in range(0, 41)]                      # 4.5 m/s toward the goal, from 10 m to 46 m
    jog = [(f, 10.0 + 0.3 * f, 5.0) for f in range(0, 41)]                       # 1.5 m/s
    short = [(f, 2.0 + 0.85 * f, 5.0) for f in range(0, 21)] + [(f, 19.0, 5.0) for f in range(21, 41)]          # fast, but stops one metre short of the line
    runs = runs_in_behind({1: fast, 2: jog, 3: short}, back)
    assert [r['track'] for r in runs] == [1] and runs[0]['speed'] >= 3.5
    assert runs_in_behind({1: fast}, {s: 60.0 for s in range(0, 30)}) == []            # the line is far beyond: nothing was passed
    assert runs_in_behind({1: [p for p in fast if p[0] % 2 == 0 and p[0] < 20]}, back) == []     # too few sightings


def test_the_opponent_line_stepping_up_or_dropping_is_named_and_a_steady_line_is_not():
    up = {s: 30.0 - s for s in range(0, 10)}
    drop = {s: 10.0 + 1.5 * s for s in range(0, 10)}
    assert line_change(up, 0, 10) == 'step_up' and line_change(drop, 0, 10) == 'drop'
    assert line_change({s: 25.0 + (s % 2) for s in range(0, 10)}, 0, 10) is None


def test_zones_balance_and_the_box():
    assert (zone_of(25), zone_of(12), zone_of(2)) == ('wing', 'half_space', 'centre')
    assert local_balance([(30, 22), (28, 20), (20, 0)], [(31, 24)], (30, 22)) == {'zone': 'wing', 'ours': 2, 'theirs': 1}
    assert box_presence([(40.0, 3.0), (30.0, 3.0), (41.0, 25.0)], [(42.0, -5.0)]) == {'ours': 2, 'theirs': 1}


def test_many_still_players_in_the_box_look_like_a_set_piece():
    still = {f: [(i, 38.0 + i * 0.5, i * 2.0 - 6) for i in range(8)] for f in range(0, 30)}
    assert standing_still(still, 0, 29)
    moving = {f: [(i, 20.0 + f * 0.8 + i * 0.5, i * 2.0 - 6) for i in range(8)] for f in range(0, 30)}
    assert not standing_still(moving, 0, 29)
