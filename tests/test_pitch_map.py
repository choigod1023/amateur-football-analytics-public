import math

import numpy as np

from app.pitch_map import MAX_RMS, DEFAULTS, apply, feet_to_metres, fit, landmarks, pitch_lines, team_shape

# A made-up perspective camera, used only by these tests: pitch metres -> normalized image coordinates.
P = [[0.0105, 0.0021, 0.52], [0.0008, -0.0140, 0.62], [0.00006, 0.0019, 1]]
DIMS = {**DEFAULTS, 'length': 90.0, 'width': 55.0}


def project(x, y):
    w = P[2][0] * x + P[2][1] * y + P[2][2]
    return (P[0][0] * x + P[0][1] * y + P[0][2]) / w, (P[1][0] * x + P[1][1] * y + P[1][2]) / w


def record(ids, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    known = landmarks(DIMS)
    points = []
    for name in ids:
        u, v = project(*known[name])
        points.append({'landmark': name, 'x': u + rng.normal(0, noise), 'y': v + rng.normal(0, noise)})
    return {'points': points, 'pitch': DIMS}


IDS = ['center', 'circle_left', 'circle_right', 'half_far', 'half_near', 'corner_l_far', 'corner_r_far', 'corner_l_near']


def test_there_are_31_landmarks_and_the_lines_close_the_pitch():
    assert len(landmarks()) == 31 and landmarks()['corner_r_near'] == (52.5, 34.0)
    assert pitch_lines()[0][0] == pitch_lines()[0][-1]


def test_a_clean_calibration_recovers_positions_in_metres():
    fitted = fit(record(IDS))
    assert fitted['rms'] < 1e-4 and fitted['points'] == 8
    u, v = project(12.0, -7.0)
    r = apply(fitted['H'], u, v)
    assert math.hypot(r[0] - 12.0, r[1] - -7.0) < 1e-3


def test_feet_use_the_bottom_centre_and_far_outside_the_pitch_gives_none():
    fitted = fit(record(IDS))
    u, v = project(10.0, 5.0)
    box = [u * 1920 - 20, v * 1080 - 90, u * 1920 + 20, v * 1080]
    m = feet_to_metres(fitted, box, 1920, 1080)
    assert m is not None and math.hypot(m[0] - 10.0, m[1] - 5.0) < 0.01
    u2, v2 = project(80.0, 5.0)
    assert feet_to_metres(fitted, [u2 * 1920 - 20, v2 * 1080 - 90, u2 * 1920 + 20, v2 * 1080], 1920, 1080) is None


def test_too_few_unknown_or_inconsistent_points_are_refused_instead_of_guessed():
    assert 'error' in fit(record(IDS[:3]))
    assert 'error' in fit({'points': [{'landmark': 'nope', 'x': .1, 'y': .1}] * 5, 'pitch': DIMS})
    bad = record(IDS)
    bad['points'][0]['x'] += 0.35                                    # one point clicked far from its landmark
    refused = fit(bad)
    assert 'error' in refused or refused['rms'] <= MAX_RMS


def test_team_shape_needs_four_players_and_reports_metres():
    assert team_shape([(0, 0), (1, 1), (2, 2)]) is None
    shape = team_shape([(0, 0), (10, 0), (10, 5), (0, 5)])
    assert (shape['depth'], shape['width'], shape['area'], shape['players']) == (10.0, 5.0, 50, 4)
    assert shape['nearest_teammate'] == 5.0 and shape['centre_x'] == 5.0


def test_a_camera_whose_horizon_crosses_the_image_still_fits():
    # image -> metres homography of a wide shot (made up, like a real one): w is negative for pitch points when the last entry is fixed to 1
    h_real = np.array([[-19.6486, 2.9627, 8.0653], [-1.3896, -73.3724, 56.8509], [-0.0347, -1.5016, 1.0]])
    inv = np.linalg.inv(h_real)
    dims = {**DEFAULTS, 'length': 89.0, 'width': 62.0}
    known = landmarks(dims)
    ids = ['half_near', 'half_far', 'circle_left', 'circle_right', 'circle_near', 'circle_far', 'corner_l_far', 'corner_r_far', 'post_l_near', 'post_r_far']
    points = []
    for name in ids:
        x, y, w = inv @ np.array([*known[name], 1.0])
        points.append({'landmark': name, 'x': x / w, 'y': y / w})
    fitted = fit({'points': points, 'pitch': dims})
    assert 'H' in fitted and fitted['rms'] < 1e-3
    r = apply(fitted['H'], points[0]['x'], points[0]['y'])
    assert r is not None and math.hypot(r[0] - known['half_near'][0], r[1] - known['half_near'][1]) < 1e-3


def test_a_shifted_frame_is_looked_up_at_the_reference_position():
    fitted = fit(record(IDS))
    u, v = project(10.0, 5.0)
    box = [u * 1920 - 20, v * 1080 - 90, u * 1920 + 20, v * 1080]
    moved = [box[0] + 6, box[1] + 4, box[2] + 6, box[3] + 4]              # the whole picture moved right 6 and down 4 pixels
    m = feet_to_metres(fitted, moved, 1920, 1080, shift=(6, 4))
    assert math.hypot(m[0] - 10.0, m[1] - 5.0) < 0.01
    assert math.hypot(feet_to_metres(fitted, moved, 1920, 1080)[0] - 10.0, feet_to_metres(fitted, moved, 1920, 1080)[1] - 5.0) > 0.01


def test_a_goalkeeper_far_from_the_team_does_not_stretch_the_team_shape():
    team = [(0, 0), (10, 0), (10, 5), (0, 5), (5, 8)]
    with_keeper = team_shape(team + [(-45, 2)])
    without = team_shape(team)
    assert with_keeper['left_out'] == 1 and with_keeper['players'] == 5
    assert (with_keeper['depth'], with_keeper['width'], with_keeper['area']) == (without['depth'], without['width'], without['area'])
    assert team_shape([(0, 0), (1, 1), (2, 2), (200, 200)]) is None            # only three remain near the middle


def test_the_reference_registration_is_applied_after_the_shift():
    fitted = fit(record(IDS))
    u, v = project(10.0, 5.0)
    x, y = u * 1920, v * 1080
    box = [x - 20, y - 90, x + 20, y]
    # the photo the clicks were made on sits 7 px left and 5 px up in the reference frame: x' = x + tx
    reference_x, reference_y = x + 7, y + 5
    moved = [box[0] - 3, box[1] + 2, box[2] - 3, box[3] + 2]                 # this clip frame lies 3 px left, 2 px down of that photo
    m = feet_to_metres(fitted, [moved[0] + 7 - 7, moved[1], moved[2] + 7 - 7, moved[3]], 1920, 1080, shift=(-3, 2), bg=(1, 0, 0, 0))
    assert math.hypot(m[0] - 10.0, m[1] - 5.0) < 0.01
    fitted_ref = fit(record(IDS))
    m2 = feet_to_metres(fitted_ref, [reference_x - 20, reference_y - 90, reference_x + 20, reference_y], 1920, 1080, bg=(1, 0, -7, -5))
    assert math.hypot(m2[0] - 10.0, m2[1] - 5.0) < 0.01
