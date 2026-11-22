import math
from app.movement import MovementTracker


def player(pid='1', team='home', x=.1, y=.2):
    return dict(id=pid, team=team, x=x, y=y)


def update(t, time_s, ps, **kwargs):
    return t.update(ps, time_s, (100, 50), calibration_validated=True, teams_validated=True, timeline_reliable=True, **kwargs)


def test_real_timeline_displacement_and_feedback():
    t=MovementTracker()
    assert update(t, 0, [player()]) == ([], [])
    records, feedback=update(t, 1, [player(x=.13, y=.28)])
    assert records == [dict(id='1', team='home', displacement_m=5.0, interval_s=1.0, average_speed_m_s=5.0)]
    assert len(feedback)==1 and all(feedback[0][key] for key in ('observation','interpretation','suggestion','limitations'))


def test_unverified_or_unreliable_timeline_clears_history():
    t=MovementTracker(); update(t, 0, [player()])
    assert t.update([player(x=.12)], 1, (100,50), calibration_validated=True, teams_validated=True, timeline_reliable=False)==([], [])
    assert update(t, 2, [player(x=.12)]) == ([], [])


def test_gaps_disappearance_team_change_and_duplicates_are_not_bridged():
    t=MovementTracker(); update(t, 0, [player()]); update(t, 0.3, [])
    assert update(t, .6, [player(x=.12)]) == ([], [])
    assert update(t, .9, [player(team='away',x=.13)]) == ([], [])
    assert update(t, 1.2, [player(team='away',x=.14),player(team='away',x=.14)]) == ([], [])
    assert update(t, 1.5, [player(team='away',x=.15)]) == ([], [])
    assert update(t, 5, [player(team='away',x=.16)]) == ([], [])
    assert update(t, 4, [player(team='away',x=.17)]) == ([], [])


def test_rejects_impossible_jump_invalid_values_and_noise():
    t=MovementTracker(); update(t, 0, [player()])
    assert update(t, .5, [player(x=.9)]) == ([], [])
    assert update(t, 1, [player(x=math.nan)]) == ([], [])
    assert update(t, 1.5, [player(x=.1)]) == ([], [])
    assert update(t, 2, [player(x=.101)]) == ([], [])


def test_anchor_accumulates_short_intervals_without_using_wall_clock():
    t=MovementTracker(); update(t, 0, [player()])
    assert update(t, .1, [player(x=.101)]) == ([], [])
    records,_=update(t, .5, [player(x=.12)])
    assert records[0]['interval_s']==.5 and records[0]['average_speed_m_s']==4
