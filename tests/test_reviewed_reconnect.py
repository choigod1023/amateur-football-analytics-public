from app.reviewed_reconnect import ReviewedReconnector,alias_players,alias_teams,alias_boxes


def decisions():
    return {'approved':[{'question':'d1','pair':['1','2'],'boundary':{'end':1.,'start':2.,'before_box':[10,10,20,30],'after_box':[12,10,22,30]}}], 'blocked':[]}


def test_exact_boundary_reconnects_without_changing_observation_coordinates():
    r=ReviewedReconnector(decisions());r.update(1.,[[10,10,20,30,1]])
    mapping,events=r.update(2.,[[12,10,22,30,2]])
    assert mapping=={'2':'1'} and events[0]['action']=='linked'
    rows=[{'id':'2','team':'home','x':.3,'y':.4}]
    assert alias_players(rows,mapping)[0]=={'id':'1','source_id':'2','team':'home','x':.3,'y':.4,'identity_basis':'human_reviewed_boundary'}
    assert rows[0]['id']=='2'
    assert alias_teams({'home':[(2,3,4)]},mapping)=={'home':[(1,3,4)]}
    assert alias_boxes({2:[12,10,22,30]},mapping)=={1:[12,10,22,30]}
    assert r.update(2.2,[])[0]=={'2':'1'}
    assert alias_players([],mapping)==[]
    assert r.update(2.8,[[12,10,22,30,2]])[0]=={}


def test_human_negative_overrides_join_and_boundary_drift_is_refused():
    d=decisions();d['blocked']=[['2','1']];r=ReviewedReconnector(d)
    r.update(1.,[[10,10,20,30,1]])
    assert r.update(2.,[[12,10,22,30,2]])[0]=={}
    r=ReviewedReconnector(decisions());r.update(1.,[[100,10,110,30,1]])
    assert r.update(2.,[[12,10,22,30,2]])[0]=={}


def test_collision_preexisting_new_id_or_skipped_boundary_never_merges():
    for first,second in [([[10,10,20,30,1],[12,10,22,30,2]],[[12,10,22,30,2]]),
                         ([[10,10,20,30,1]],[[10,10,20,30,1],[12,10,22,30,2]]),
                         ([],[[12,10,22,30,2]])]:
        r=ReviewedReconnector(decisions());r.update(1.,first)
        assert r.update(2.,second)[0]=={}


def test_collision_and_rewind_retire_active_alias():
    for t,rows in [(2.2,[[10,10,20,30,1],[12,10,22,30,2]]),(.5,[[12,10,22,30,2]])]:
        r=ReviewedReconnector(decisions());r.update(1.,[[10,10,20,30,1]]);r.update(2.,[[12,10,22,30,2]])
        assert not r.update(t,rows)[0]
        assert not r.update(2.4,[[12,10,22,30,2]])[0]


def test_two_approved_boundaries_cannot_create_duplicate_output_identity():
    d=decisions()
    d['approved'].append({'question':'d2','pair':['1','3'],'boundary':d['approved'][0]['boundary']})
    r=ReviewedReconnector(d);r.update(1.,[[10,10,20,30,1]])
    assert r.update(2.,[[12,10,22,30,2],[12,10,22,30,3]])[0]=={}
