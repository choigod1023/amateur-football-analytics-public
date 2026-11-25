import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.keeper_zone import KeeperZone, zone_goal  # noqa: E402

L = 89.0


def run(kz, seconds, people, direction=1, dt=0.2, t0=0.0):
    marks = []
    for k in range(int(seconds / dt)):
        marks = kz.update(t0 + k * dt, direction, people(k))
    return marks


def test_zone_geometry():
    assert zone_goal(-43.0, 0.0, L) == -1
    assert zone_goal(43.0, 5.0, L) == 1
    assert zone_goal(-39.0, 9.16, L) == -1          # edge of the goal area counts
    assert zone_goal(-38.9, 0.0, L) == 0            # deeper than 5.5 m
    assert zone_goal(-43.0, 9.5, L) == 0            # wider than the goal area
    assert zone_goal(-46.0, 0.0, L) == 0            # more than the slack behind the line
    assert zone_goal(0.0, 0.0, L) == 0


def test_stayer_is_marked_with_goal_and_side_even_without_team_letter():
    kz = KeeperZone(L)
    marks = run(kz, 12.0, lambda k: [(7, -42.0, 1.0, None)], direction=1)
    assert len(marks) == 1
    m = marks[0]
    assert (m['id'], m['goal'], m['side'], m['letter']) == (7, 'left', 'own', None)
    # the same man in the other half (direction -1): the left goal is the opposing goal
    kz = KeeperZone(L)
    assert run(kz, 12.0, lambda k: [(7, -42.0, 1.0, 'B')], direction=-1)[0]['side'] == 'opp'


def test_not_marked_before_min_seen_and_no_past_only_leak():
    kz = KeeperZone(L)
    assert run(kz, 4.0, lambda k: [(7, -42.0, 0.0, None)]) == []
    assert len(run(kz, 2.0, lambda k: [(7, -42.0, 0.0, None)], t0=4.0)) == 1


def test_field_player_passing_through_is_not_marked():
    kz = KeeperZone(L)

    def walker(k):                                   # 2 s in the zone out of 12 s
        return [(3, -42.0 if 20 <= k < 30 else -20.0, 0.0, 'B')]
    assert run(kz, 12.0, walker) == []


def test_one_mark_per_goal_and_both_goals_independent():
    kz = KeeperZone(L)
    ppl = lambda k: [(1, -42.0, 0.0, None), (2, -41.0, 2.0, 'A'), (9, 42.0, 0.0, None)]
    marks = run(kz, 12.0, ppl)
    assert sorted(m['goal'] for m in marks) == ['left', 'right']
    assert kz.crowded == 1 and kz.candidates == 3
    left = [m for m in marks if m['goal'] == 'left'][0]
    assert left['id'] == 1                           # equal share and span: the lower id is kept (stable)


def test_leaving_the_zone_ends_the_mark_and_old_tracks_are_forgotten():
    kz = KeeperZone(L)
    run(kz, 12.0, lambda k: [(7, -42.0, 0.0, None)])
    marks = run(kz, 12.0, lambda k: [(7, -20.0, 0.0, None)], t0=12.0)
    assert marks == []
    run(kz, 12.0, lambda k: [], t0=24.0)
    assert kz.history == {} and kz.seen == {}


def test_only_past_frames_are_used():
    a, b = KeeperZone(L), KeeperZone(L)
    seq = [(-42.0 if k < 70 else -10.0) for k in range(100)]
    ma = [a.update(k * 0.2, 1, [(5, seq[k], 0.0, None)]) for k in range(100)]
    seq2 = seq[:60] + [-42.0] * 40                    # the future differs, the first 60 frames do not
    mb = [b.update(k * 0.2, 1, [(5, seq2[k], 0.0, None)]) for k in range(100)]
    assert ma[:60] == mb[:60]


def test_safe_wrapper_warns_once_and_returns_empty_marks_on_exception():
    from app.keeper_zone import SafeKeeperZone
    warnings = []
    safe = SafeKeeperZone(KeeperZone(L), warn=warnings.append)

    def broken():
        raise ValueError('bad foot point')

    assert safe.update(0.0, 1, broken) == []
    assert safe.update(0.2, 1, broken) == []
    assert len(warnings) == 1 and 'ValueError' in warnings[0]
    assert safe.failed_frames == 2
    # a good frame afterwards works again
    assert safe.update(0.4, 1, lambda: [(7, -42.0, 1.0, None)]) == []   # not enough history yet, but no exception


def test_safe_wrapper_marks_like_the_plain_class_when_nothing_fails():
    from app.keeper_zone import SafeKeeperZone
    plain, safe = KeeperZone(L), SafeKeeperZone(KeeperZone(L), warn=lambda m: None)
    for k in range(60):
        people = [(7, -42.0, 1.0, None)]
        a = plain.update(k * 0.2, 1, people)
        b = safe.update(k * 0.2, 1, lambda: people)
        assert a == b
    assert len(a) == 1 and safe.failed_frames == 0
