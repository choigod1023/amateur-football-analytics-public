from app.event_miner import mine_events
from app.review_text import event_bullets, index_title


def metrics(centre=10.0, isolation=6.0, back=20.0, leader=7):
    return {'centre': centre, 'leader_isolation': isolation, 'opponent_back_line': back, 'leader': leader}


def test_a_half_gives_runs_isolation_and_goal_moments_apart_from_each_other():
    series_team = {s: metrics() for s in range(0, 400)}
    for s in range(100, 125):
        series_team[s] = metrics(isolation=22.0, leader=9)                                    # a player left alone for 25 s
    series_other = {s: metrics(back=18.0) for s in range(0, 400)}
    fast = [(f, 5.0 + 0.9 * f, 4.0) for f in range(0, 41)]                                     # a run past the line at second 8
    late = [(f, 5.0 + 0.9 * (f - 1000), 4.0) for f in range(1000, 1041)]                      # another one near second 208
    events = mine_events({1: fast, 2: late}, {}, series_team, series_other, [300.0], offset=0.0)
    kinds = [e['kind'] for e in events]
    assert kinds.count('goal') == 1 and 'run' in kinds and 'isolated' in kinds
    times = [e['time'] for e in events]
    assert times == sorted(times) and all(b - a >= 20 for a, b in zip(times, times[1:]))
    goal = next(e for e in events if e['kind'] == 'goal')
    assert goal['end'] == 303.0 and goal['goal_follow'] and goal['polarity'] == 'goal'          # no run leads into this goal, so it is a moment of its own
    run = next(e for e in events if e['kind'] == 'run')
    assert run['end'] == run['time'] + 14.0 and not run['goal_follow']


def test_an_event_followed_by_a_goal_runs_on_to_the_goal_and_poor_events_are_capped():
    series_team = {s: metrics() for s in range(0, 600)}
    series_other = {s: metrics(back=18.0) for s in range(0, 600)}
    run = [(f, 5.0 + 0.9 * f, 4.0) for f in range(0, 41)]
    events = mine_events({1: run}, {}, series_team, series_other, [40.0], offset=0.0)
    first = next(e for e in events if e['kind'] == 'run')
    assert first['goal_follow'] and first['end'] == 43.0 and not any(e['kind'] == 'goal' for e in events)      # the run carries the goal
    conceded = {i: [(f, 5.0 + 0.9 * (f - i * 400), 4.0) for f in range(i * 400, i * 400 + 41)] for i in range(1, 6)}
    capped = mine_events({}, conceded, {s: metrics() for s in range(0, 2400)}, {s: metrics(back=18.0) for s in range(0, 2400)}, [], offset=0.0, max_poor=3)
    assert len([e for e in capped if e['polarity'] == 'poor']) == 2          # one kind of moment cannot fill the half: at most two runs the team allowed


def test_the_bullets_are_three_short_lines_without_metre_values():
    for kind in ('run', 'conceded_run', 'isolated', 'line_drop', 'goal'):
        bullets = event_bullets({'kind': kind}, {'side': 'near', 'back_line': 34.0, 'between': 2, 'box_ours': 4})
        assert len(bullets) == 3 and all(len(b) <= 46 and not any(ch.isdigit() for ch in b) for b in bullets)
    assert '가까운 쪽 측면' in event_bullets({'kind': 'run'}, {'side': 'near'})[0]
    assert '낮게 내려앉아' in event_bullets({'kind': 'goal'}, {'back_line': 34.0})[1]
    assert index_title({'kind': 'run', 'title': '침투', 'goal_follow': True}, '1:00') == '침투 · 골로 이어짐'


def test_an_attack_that_brings_players_into_the_box_is_a_moment_and_can_carry_a_goal():
    from app.event_miner import _box_attacks
    inside = {i: [(f, 40.0, float(i)) for f in range(100, 140)] for i in range(4)}           # four players stand in the box from second 20 to 28
    assert _box_attacks(inside, 89.0, 5.0) == [(20, 4)]
    assert _box_attacks({0: [(f, 40.0, 0.0) for f in range(100, 140)]}, 89.0, 5.0) == []     # one player is not an attack
    series = {s: metrics() for s in range(0, 200)}
    events = mine_events(inside, {}, series, {s: metrics(back=18.0) for s in range(0, 200)}, [27.0], offset=0.0)
    box = next(e for e in events if e['kind'] == 'box_attack')
    assert box['goal_follow'] and box['goal_at'] == 27.0 and not any(e['kind'] == 'goal' for e in events)
    assert event_bullets(box, {'side': 'near'})[0].startswith('가까운 쪽 측면에서 박스 안')
