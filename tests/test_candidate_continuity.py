from app.candidate_continuity import CandidateContinuity


def test_only_bounded_intermittent_unknown_on_visible_id():
    c=CandidateContinuity()
    for _ in range(3): assert c.update({'1':0})['1'] == 0
    assert c.update({'1':None})['1'] == 0
    assert c.update({'1':None})['1'] == 0
    assert c.update({'1':None})['1'] is None
    assert c.update({}) == {}
    assert c.update({'1':None})['1'] is None


def test_conflicting_group_revokes_hint_not_force_identity():
    c=CandidateContinuity()
    for _ in range(3): c.update({'1':0})
    assert c.update({'1':1})['1'] is None
    assert c.update({'1':None})['1'] is None


def test_hold_only_missing_crops_and_clear_on_gap():
    c=CandidateContinuity()
    for t in (1.0,1.1,1.2): c.update({'1':0},timestamp=t,holdable=set())
    assert c.update({'1':None},timestamp=1.3,holdable=set())['1'] is None
    assert c.update({'1':None},timestamp=1.4,holdable={'1'})['1'] == 0
    assert c.update({'1':None},timestamp=3.0,holdable={'1'})['1'] is None
