from app.tactical_feedback import breakthrough_runs, estimate_missing, feedback, open_lanes, segment_distance, speeds, team_lines

PITCH = {'length': 90.0, 'width': 60.0}


def test_segment_distance_uses_the_closest_point_of_the_segment():
    assert segment_distance((5, 3), (0, 0), (10, 0)) == 3
    assert segment_distance((-4, 3), (0, 0), (10, 0)) == 5          # beyond the start: distance to the start point


def test_missing_players_are_carried_along_with_the_team_and_never_stacked_on_a_seen_teammate():
    present = [(float(x), float(y)) for x in (-20, 0, 20) for y in (-10, 10)]            # 6 seen
    recent = [(0.5, 10.5, 2.0), (30.0, 0.0, 4.0), (60.0, 0.0, 6.0)]                      # the first stands on a seen teammate
    out = estimate_missing(present, recent, PITCH, team_size=8, drift=(1.0, 0.0))
    assert len(out) == 1 and out[0]['kind'] == 'recent' and (out[0]['x'], out[0]['y']) == (31.0, 0.0)   # the player nobody saw is not invented
    out = estimate_missing(present, recent, PITCH, team_size=8, drift=(1.0, 0.0), fill_holes=True)
    assert len(out) == 2 and out[1]['kind'] == 'gap'                                                         # the third one is beyond the pitch end, so the hole is filled instead
    assert estimate_missing(present, recent, PITCH, team_size=6) == [] and estimate_missing([], recent, PITCH) == []


def test_a_gap_fill_goes_where_the_team_has_the_largest_hole():
    present = [(-20.0, -10.0), (-20.0, 10.0), (20.0, -10.0), (20.0, 10.0), (0.0, -10.0)]
    out = estimate_missing(present, [], PITCH, team_size=6, fill_holes=True)
    assert len(out) == 1 and abs(out[0]['x']) < 8 and out[0]['y'] > 0


def test_open_lanes_need_no_opponent_close_to_the_line():
    team = [(0.0, 0.0), (20.0, 0.0), (0.0, 20.0)]
    blocked = open_lanes(team, [(10.0, 0.5)], direction=1)
    assert {(l['from'], l['to']) for l in blocked} == {(0, 2), (2, 0), (1, 2), (2, 1)}   # the 0-1 lane is blocked
    clear = open_lanes(team, [], direction=1)
    forward = [l for l in clear if l['forward']]
    assert [(l['from'], l['to']) for l in forward] == [(0, 1), (2, 1)]


def test_team_lines_cut_the_team_into_three_groups():
    points = [(-40, 0)] + [(-20, y) for y in (-15, -5, 5, 15)] + [(0, y) for y in (-10, 0, 10)] + [(25, -5), (25, 5)]
    lines = team_lines(points, direction=1)
    assert lines['sizes'] == [4, 3, 2] and lines['defence'] == -20 and lines['attack'] == 25
    assert team_lines(points[:4]) is None


def test_speeds_and_a_breakthrough_run_that_beats_a_defender():
    path = [(f, f * 1.4, 0.0) for f in range(0, 16)]                                      # 7 m/s along +x
    assert round(speeds(path)[10], 1) == 7.0
    def opponents(frame):
        return [(10.0, 0.5)]                                       # a defender who stays where he is
    runs = breakthrough_runs(path, opponents, direction=1)
    assert runs and runs[0]['beaten'] == 1


def test_feedback_names_the_number_of_estimated_players_and_the_gaps():
    notes = feedback('A', 9.5, 1.5, {'defence': -20, 'midfield': 2, 'attack': 30, 'sizes': [4, 4, 2], 'defence_to_midfield': 25, 'midfield_to_attack': 30},
                     {'open': 10, 'forward_open': 1.0, 'possible': 40})
    text = ' '.join(notes)
    assert '9.5명' in text and '1.5명' in text and '25m' in text and '고립' in text and '앞쪽' in text
