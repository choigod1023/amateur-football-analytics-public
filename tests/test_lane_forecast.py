from app.lane_forecast import forecast, positions


def frames(carrier_path, mate_path, defender_path, count=30):
    by_frame = {}
    for f in range(count):
        by_frame[f] = {'B': [('c', *carrier_path(f)), ('m', *mate_path(f))], 'A': [('d', *defender_path(f))] + [('x%d' % i, -30.0 - i, 20.0) for i in range(3)]}
    return by_frame


def test_a_defender_running_onto_the_line_closes_the_lane_in_the_forecast_and_not_before():
    # the carrier at (0,0), the mate at (20,0); a defender at (10, 8) runs toward the line at 4 m/s (5 frames per second)
    by_frame = frames(lambda f: (0.0, 0.0), lambda f: (20.0, 0.0), lambda f: (10.0, 8.0 - 0.8 * f))
    lanes = forecast(by_frame, 'B', 'A', 1, 5.0, 5, 'c', horizon=1.5)
    mate = next(l for l in lanes if l['track'] == 'm')
    assert mate['open_now'] and not mate['open_later']                     # at frame 5 he is 4 m from the line and open; after 1.5 s at 4 m/s he has crossed it


def test_positions_cap_the_speed_and_give_zero_for_a_player_seen_once():
    by_frame = {0: {'B': [('a', 0.0, 0.0)]}, 5: {'B': [('a', 40.0, 0.0), ('b', 3.0, 3.0)]}}
    p = positions(by_frame, 'B', 1, 5.0, 5)
    assert abs(p['a'][1][0] - 7.0) < 1e-6 and p['b'][1] == (0.0, 0.0)
