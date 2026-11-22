import numpy as np
from app.identity_guard import IdentityGuard


def picture(boxes):
    image=np.zeros((150,180,3),dtype=np.uint8)
    for box,colour in boxes:
        x1,y1,x2,y2=map(int,box);image[y1:y2,x1:x2]=colour
    return image


def test_large_appearance_and_geometry_change_segments_without_inventing_track():
    guard=IdentityGuard()
    a=[20,20,30,40];b=[20,20,45,75]
    guard.update(0,picture([(a,(0,0,255))]),np.array([[*a,1]],dtype=np.float32))
    rows,events=guard.update(.2,picture([(b,(255,0,0))]),[[*b,1]])
    assert rows[0,4]==1_000_000 and len(events)==1
    assert events[0]['action']=='split'
    assert rows.dtype==np.float64 and events[0]['identity_verified'] is False
    rows,events=guard.update(.4,picture([(b,(255,0,0))]),[[*b,1]])
    assert rows[0,4]==1_000_000 and events==[]


def test_colour_change_without_geometry_does_not_split():
    guard=IdentityGuard();box=[20,20,35,55]
    guard.update(0,picture([(box,(0,0,255))]),[[*box,1]])
    rows,events=guard.update(.2,picture([(box,(255,0,0))]),[[*box,1]])
    assert rows[0,4]==1 and not events


def test_overlap_freezes_appearance_and_does_not_claim_disambiguation():
    guard=IdentityGuard();a=[20,20,30,40];b=[20,20,45,75]
    guard.update(0,picture([(a,(0,0,255))]),[[*a,1]])
    old=[p.copy() for p in guard.tracks[1]['appearance']]
    rows,events=guard.update(.2,picture([(b,(255,0,0))]),[[*b,1],[*b,2]])
    assert not events and rows[:,4].tolist()==[1,2]
    assert all(np.array_equal(a,b) for a,b in zip(old,guard.tracks[1]['appearance']))


def test_absence_never_creates_rows_and_history_expires():
    guard=IdentityGuard(ttl=1);box=[20,20,35,55]
    guard.update(0,picture([(box,(0,0,255))]),[[*box,1]])
    rows,events=guard.update(2,picture([]),np.empty((0,8)))
    assert rows.shape==(0,8) and not events and guard.tracks=={}


def test_partial_legs_box_to_full_person_is_review_not_identity_split():
    guard=IdentityGuard();legs=[30,50,40,65];full=[28,20,45,65]
    guard.update(0,picture([(legs,(0,0,255))]),[[*legs,1]])
    rows,events=guard.update(.2,picture([(full,(255,0,0))]),[[*full,1]])
    assert rows[0,4]==1
    assert len(events)==1 and events[0]['action']=='review'
    assert events[0]['reason']=='partial_full_box_change'
    assert events[0]['old_segment']==events[0]['new_segment']
