from app.position_guard import PositionGuard
from app.position_guard import DisplayPositionGuard


def test_jump_is_omitted_not_interpolated_and_can_recover():
    guard = PositionGuard()
    assert guard.filter(0, {'A': [(1, 0., 0.)]})[1] == 0
    rows, rejected = guard.filter(.2, {'A': [(1, 10., 0.)]})
    assert rows['A'] == [] and rejected == 1
    # Two distant observations cannot establish a physically continuous path.
    assert guard.filter(.4, {'A': [(1, 10.1, 0.)]})[1] == 1
    assert guard.filter(.8, {'A': [(1, 10.1, 0.)]})[1] == 0  # expired history


def test_rejected_outlier_does_not_hide_return_to_accepted_position():
    guard = PositionGuard()
    guard.filter(0, {'A': [(1, 0., 0.)]})
    assert guard.filter(.2, {'A': [(1, 10., 0.)]})[1] == 1
    assert guard.filter(.4, {'A': [(1, .1, 0.)]}) == ({'A': [(1, .1, 0.)]}, 0)


def test_empty_and_nonfinite_observations_preserve_bounded_anchor_without_emitting():
    guard = PositionGuard()
    guard.filter(0, {'A': [(1, 0., 0.)]})
    assert guard.filter(.2, {'A': []}) == ({'A': []}, 0)
    assert guard.filter(.4, {'A': [(1, float('nan'), 0.)]}) == ({'A': []}, 1)
    assert guard.filter(.6, {'A': [(1, 10., 0.)]}) == ({'A': []}, 1)
    assert guard.filter(.8, {'A': [(1, 10., 0.)]})[1] == 0


def test_duplicate_time_is_not_a_new_observation_and_rewind_resets_domain():
    guard = PositionGuard()
    guard.filter(10, {'A': [(1, 0., 0.)]})
    assert guard.filter(10, {'A': [(1, 50., 0.)]}) == ({'A': []}, 1)
    assert guard.filter(float('nan'), {'A': [(1, 50., 0.)]}) == ({'A': []}, 1)
    assert guard.filter(0, {'A': [(1, 50., 0.)]}) == ({'A': [(1, 50., 0.)]}, 0)


def test_duplicate_id_is_not_emitted_twice():
    guard = PositionGuard()
    assert guard.filter(0, {'A': [(1, 0., 0.), (1, 0., 0.)]}) == ({'A': [(1, 0., 0.)]}, 1)


def test_missing_and_team_change_do_not_invent_continuity():
    guard = PositionGuard()
    guard.filter(0, {'A': [(1, 0., 0.)]})
    assert guard.filter(.2, {'A': []})[0]['A'] == []
    assert guard.filter(.4, {'B': [(1, 30., 0.)]})[1] == 0


def test_display_filter_reset_falls_back_to_raw_or_omits_without_new_teleport():
    guard=DisplayPositionGuard()
    guard.filter(0,{'A':[(1,0,0)]},{'A':[(1,0,0)]})
    out,counts=guard.filter(.2,{'A':[(1,2,0)]},{'A':[(1,3,0)]})
    assert out['A']==[(1,2,0)] and counts['raw_fallbacks']==1
    out,counts=guard.filter(.4,{'A':[(1,6,0)]},{'A':[(1,7,0)]})
    assert out['A']==[] and counts['omitted']==1


def test_display_drop_does_not_clear_the_last_accepted_anchor():
    guard=DisplayPositionGuard()
    guard.filter(0, {'A':[(1,0,0)]}, {'A':[(1,0,0)]})
    for t,x in ((.2,10),(.4,10.1)):
        out,counts=guard.filter(t,{'A':[(1,x,0)]},{'A':[(1,x,0)]})
        assert out['A']==[] and counts['omitted']==1
    out,counts=guard.filter(.6,{'A':[(1,.1,0)]},{'A':[(1,.1,0)]})
    assert out['A']==[(1,.1,0)] and counts['omitted']==0


def test_display_history_expires_and_time_rewind_restarts():
    guard=DisplayPositionGuard()
    guard.filter(0, {'A':[(1,0,0)]}, {'A':[(1,0,0)]})
    assert guard.filter(.2,{'A':[]},{'A':[]})[0]['A']==[]
    assert guard.filter(.8,{'A':[(1,50,0)]},{'A':[(1,50,0)]})[0]['A']==[(1,50,0)]
    assert guard.filter(.8,{'A':[(1,0,0)]},{'A':[(1,0,0)]})[0]['A']==[]
    assert guard.filter(0,{'A':[(1,0,0)]},{'A':[(1,0,0)]})[0]['A']==[(1,0,0)]


def test_real_replay_evaluator_preserves_observations_and_measures_recovery():
    from scripts.evaluate_position_recovery import evaluate, LegacyPositionGuard, LegacyDisplayPositionGuard
    rows=[{'time':t,'raw_positions':{'home':[(1,x,0)],'away':[]}} for t,x in ((0,0),(.2,10),(.4,.1))]
    old=evaluate(rows,LegacyPositionGuard,LegacyDisplayPositionGuard)
    new=evaluate(rows)
    assert old['metrics']['retained']==1
    assert new['metrics']['retained']==2
    assert new['metrics']['output_coordinates_not_in_input']==0
    assert new['frames'][1]['accepted']['home']==[]
    assert new['frames'][2]['accepted']['home']==[(1,.1,0)]
