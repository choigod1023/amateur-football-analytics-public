from app import team_tactics as tt


def team(points):
    return [(i, u, v) for i, (u, v) in enumerate(points)]


def line_up(depth_shift=0.0, width=30.0, n=10):
    return [(-20 + depth_shift + 4 * i, -width / 2 + width * (i % 5) / 4) for i in range(n)]


def test_hull_area_and_shape():
    assert tt.hull_area([(0, 0), (10, 0), (10, 10), (0, 10), (5, 5)]) == 100.0 and tt.hull_area([(0, 0), (1, 1)]) == 0.0
    s = tt.shape(line_up())
    assert s['n'] == 10 and round(s['depth']) == 36 and round(s['width']) == 24 or s['width'] > 20
    assert tt.shape(line_up(n=5)) is None


def test_the_goalkeeper_far_behind_is_not_part_of_the_depth():
    with_keeper = [(-42.0, 0.0)] + [(-20 + 3 * i, -10 + 3 * i) for i in range(9)]
    s = tt.shape(with_keeper)
    assert round(s['depth']) == 24 and s['n'] == 10


def test_series_zones_territory_windows_and_surges():
    frames = {}
    for second in range(0, 40):
        shift = 0.0 if second < 20 else 14.0                                      # the team moves 14 m forward at second 20
        ours = [(i, (-10 + 3 * i + shift) * 1.0, -12 + 3 * i) for i in range(10)]
        theirs = [(100 + i, -(15 + 3 * i), 12 - 3 * i) for i in range(10)]
        frames[second * 5] = {'B': ours, 'A': theirs}
    series = tt.seconds_series(frames, 'B', 'A', 1, 5.0, 200)
    assert len([r for r in series.values() if r['ours']]) == 40
    zones = tt.zone_shares(series)
    assert abs(sum(sum(r) for r in zones) - 100.0) < 1.0
    assert tt.territory(series) is not None
    w = tt.windows(series, 20, 'ours', 'centre_u')
    assert len(w) == 2 and w[1][1] - w[0][1] > 10
    found = tt.surges(series, window=6, distance=10.0, minimum_gap=20)
    assert found and found[0][1] == 'forward'
    assert tt.tightness(series)


def test_open_side_counts_the_seconds_without_a_defender_in_a_lane():
    pts = [(-30.0, -20.0), (-29.0, -18.0), (-28.0, -10.0), (-27.0, -12.0)] + [(-10 + i, 0.0) for i in range(6)]      # the four deepest all stand on the left or centre-left
    series = {0: {'ours_points': pts}}
    shares = tt.open_side(series, 'ours_points')
    assert shares['right'] == 100.0 and shares['left'] == 0.0
