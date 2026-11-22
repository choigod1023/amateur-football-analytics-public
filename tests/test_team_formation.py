from app.team_formation import control_grid, control_summary, control_series, formation, formation_by_window


def line(u, vs):
    return [(u, v) for v in vs]


def test_a_442_is_read_as_442():
    points = [(-42, 0)] + line(-25, (-24, -8, 8, 24)) + line(-5, (-24, -8, 8, 24)) + line(15, (-8, 8))
    answer = formation(points)
    assert answer['text'] == '4-4-2'
    assert answer['goalkeeper_removed'] is True


def test_a_433_is_read_as_433():
    points = [(-42, 0)] + line(-25, (-24, -8, 8, 24)) + line(-6, (-14, 0, 14)) + line(18, (-20, 0, 20))
    assert formation(points)['text'] == '4-3-3'


def test_four_lines_are_used_when_the_depths_really_form_four_groups():
    points = [(-42, 0)] + line(-28, (-20, -7, 7, 20)) + line(-14, (-8, 8)) + line(2, (-16, 0, 16)) + line(20, (0,))
    assert formation(points)['text'] == '4-2-3-1'


def test_too_few_players_gives_no_formation():
    assert formation(line(-10, (-20, -10, 0, 10, 20, 25))) is None


def test_formation_by_window_reports_the_most_common_answer():
    points = [(-42, 0)] + line(-25, (-24, -8, 8, 24)) + line(-5, (-24, -8, 8, 24)) + line(15, (-8, 8))
    series = {s: {'ours_points': points} for s in range(10)}
    window = formation_by_window(series, length=300)[0]
    assert window[1] == '4-4-2' and window[2] == 1.0 and window[3] == 10


def test_a_team_that_stands_in_the_opponent_half_controls_more_of_it():
    ours = line(15, (-20, -10, 0, 10, 20))
    theirs = line(-15, (-20, -10, 0, 10, 20))
    grid = control_grid(ours, theirs)
    summary = control_summary(grid)
    assert summary['opponent_third'] > 0.9 and summary['own_third'] < 0.1
    assert abs(summary['total'] - 0.5) < 0.1


def test_control_is_symmetric_for_mirrored_teams():
    a = line(10, (-20, -10, 0, 10, 20))
    b = [(-u, -v) for u, v in a]
    total = control_summary(control_grid(a, b))['total']
    assert abs(total - 0.5) < 0.01


def test_control_series_turns_the_opponent_into_our_frame():
    ours = line(10, (-20, -10, 0, 10, 20))
    theirs_own_frame = [(-u, -v) for u, v in line(-10, (-20, -10, 0, 10, 20))]   # their own frame: they stand 10 m in front of their goal... mirrored
    series = {0: {'ours_points': ours, 'theirs_points': theirs_own_frame}}
    out = control_series(series)
    assert 0 in out and 0.0 <= out[0]['total'] <= 1.0
