import numpy as np
from app.crossing_identity import decide_crossing


def sequence(times,direction,color):
    d=[np.array(color,dtype=float)]*6
    return [{'time':t,'box':[50+direction*20*t,0,60+direction*20*t,40],'descriptor':d} for t in times]


def data():
    return [sequence([0,.2,.4],1,[1,0]),sequence([0,.2,.4],-1,[0,1])],[sequence([.8,1,1.2],1,[1,0]),sequence([.8,1,1.2],-1,[0,1])]


def test_consistent_multiframe_motion_and_appearance_keeps_identity():
    a,b=data();r=decide_crossing(a,b);assert r['decision']=='keep_candidate' and r['available_at']==1.2


def test_injected_swap_is_only_candidate_not_verified_identity():
    a,b=data();r=decide_crossing(a,b[::-1]);assert r['decision']=='swap_candidate' and not r['identity_verified']


def test_same_shirt_appearance_cannot_confirm_motion_only_swap():
    a,b=data()
    for s in a+b:
        for r in s:r['descriptor']=[np.array([1.,0.])]*6
    assert decide_crossing(a,b[::-1])['decision']=='review'


def test_two_frames_or_crowded_crop_cannot_confirm():
    a,b=data();assert decide_crossing(a,[b[0][:2],b[1]])['decision']=='review'
    b[0][0]['crowded']=True;assert decide_crossing(a,b)['decision']=='review'


def test_conflicting_appearance_and_motion_abstains():
    a,b=data()
    for s in b:
        for r in s:r['descriptor']=[x[::-1] for x in r['descriptor']]
    assert decide_crossing(a,b)['reason']=='appearance_motion_disagree'
