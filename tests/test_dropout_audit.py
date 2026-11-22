import pytest
from app.dropout_audit import analyse, visible, reconnect_candidates


def frame(t, raw=True, positioned=True, kept=True, display=True):
    p={'id':'1','team':'home','x':.5,'y':.5}
    return {'time':t,'source_tracks':[[1,1,3,5,1]] if raw else [],
            'raw_positions':{'home':[[1,0,0]] if positioned else [],'away':[]},
            'unlinked_players':[p] if kept else [],'players':[p] if kept else [],
            'display_players':[p] if display else [],'camera_ready':True,'position_rejected':int(not kept)}


@pytest.mark.parametrize('kwargs,reason',[
    ({'raw':False},'raw_tracker_observation_absent'),
    ({'positioned':False},'team_or_projection_unresolved'),
    ({'kept':False},'position_guard_rejected'),
    ({},'display_filter_or_coordinate_rejected')])
def test_loss_reason_tracks_stage_evidence(kwargs,reason):
    r=analyse([frame(0),frame(.2,display=False,**kwargs)])
    assert r['reason_counts']=={reason:1}


def test_explicit_team_exclusion_and_alias_change():
    next_frame=frame(.2,positioned=False,display=False)
    next_frame['track_outcomes']=[{'id':'1','projection_status':'team_excluded'}]
    assert analyse([frame(0),next_frame])['reason_counts']=={'team_vote_excluded':1}
    next_frame=frame(.2,display=False)
    next_frame['identity_aliases']={'1':'2'}
    assert analyse([frame(0),next_frame])['reason_counts']=={'reviewed_alias_changed':1}


def test_capacity_does_not_create_map_losses():
    f=frame(0)
    f['unlinked_players']=[{'id':str(i),'team':'home','x':.5,'y':.5} for i in range(12)]
    r=analyse([f])
    assert r['stage_totals']['coaching_capacity_blocked_frames']==1
    assert r['display_loss_events']==0


def test_invalid_positions_and_nonmonotonic_times():
    assert visible([{'id':'x','x':float('nan'),'y':0}])=={}
    with pytest.raises(ValueError):analyse([frame(.2),frame(.2)])


def test_short_tracks_not_automatically_reconnected():
    assert reconnect_candidates([frame(0),frame(.2)])==[]


def test_missing_track_with_detection_is_only_a_clue():
    f=frame(.2,raw=False,display=False)
    f['tracking_detections']=[[1,1,3,5,.8,0]]
    r=analyse([frame(0),f])
    assert r['reason_counts']=={'raw_tracker_observation_absent':1}
    assert r['raw_absence_detection_clues']['with_nearby_detection']==1
    assert not r['events'][0]['detection_evidence']['identity_verified']


def test_display_recovery_loss_is_separate():
    f=frame(0,raw=False)
    f['display_players'][0]['observation_kind']='low_confidence_recovery'
    assert analyse([f,frame(.2,raw=False,display=False)])['reason_counts']=={'low_confidence_recovery_expired':1}
