from scripts.report_motion import box_path, choose_key_track, coverage


def rows(frames, x0=100.0, step=2.0):
    return [{'frame': f, 'team': 'B', 'box': [x0 + step * f, 100.0, x0 + step * f + 20, 160.0]} for f in frames]


def test_a_path_bridges_gaps_and_smooths_but_does_not_cross_long_gaps():
    path = box_path(rows(list(range(0, 10)) + list(range(30, 40))), 0, 39)
    assert coverage(path, 0, 39) == 1.0 and abs(path[20][0] - (100 + 2 * 20)) < 1.5          # a straight line across the 20-frame gap
    far = box_path(rows(list(range(0, 10)) + list(range(100, 110))), 0, 109)
    assert 50 not in far and 5 in far


def test_the_key_track_falls_back_to_the_most_advanced_covered_track():
    tracks = {'1': rows(range(0, 5)), '2': rows(range(0, 40)), '3': rows(range(0, 40), x0=300.0)}
    tid, path = choose_key_track(tracks, 1, 'B', 0, 39, {1: 20.0, 2: 10.0, 3: 30.0})
    assert tid == '3' and coverage(path, 0, 39) == 1.0                                          # the preferred track covers too little
    tid, _ = choose_key_track(tracks, 2, 'B', 0, 39, {1: 20.0, 2: 10.0, 3: 30.0})
    assert tid == '2'
