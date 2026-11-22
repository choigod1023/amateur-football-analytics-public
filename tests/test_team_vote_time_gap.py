import numpy as np
import pytest
from scripts import run_live_feedback_identity as live


FRAME = np.zeros((100,100,3), dtype=np.uint8)
TRACKS = np.array([[10,10,20,40,430],[70,10,80,40,2]],dtype=float)


def voter(monkeypatch, guarded=False):
    monkeypatch.setattr(live,'load_model',lambda _: {'classes':['team_a','team_b']})
    current = [.1,.9]
    monkeypatch.setattr(live,'predict',lambda m,x:np.tile(current,(len(x),1)))
    return live.TeamVotes('test',guarded=guarded), current


@pytest.mark.parametrize('guarded',[False,True])
def test_430_long_gap_restarts_vote_instead_of_retaining_seventeen_old_votes(monkeypatch, guarded):
    votes, probability = voter(monkeypatch, guarded)
    for i in range(17):
        votes.observe_many(FRAME,TRACKS,t=20.2+i*.2)
    assert votes.label(430)=='B'
    # Keep the other ID observed during the 9.2 s absence of ID430.
    for i in range(1,46):
        votes.observe_many(FRAME,TRACKS[1:],t=23.4+i*.2)
    other = votes.votes[2].copy()
    probability[:]=[.99,.01]
    votes.observe_many(FRAME,TRACKS,t=32.6)
    assert votes.votes[430]=={'A':1}
    assert votes.label(430) is None
    assert votes.votes[2]['B']==other['B']
    assert votes.last_resets[0]['id']=='430'
    assert votes.last_resets[0]['gap_s']==pytest.approx(9.2)
    votes.observe_many(FRAME,TRACKS[:1],t=32.8)
    assert votes.label(430) is None
    votes.observe_many(FRAME,TRACKS[:1],t=33.)
    assert votes.label(430)=='A'


def test_short_gap_preserves_counts_and_empty_frame_advances_clock(monkeypatch):
    votes,_=voter(monkeypatch)
    votes.observe_many(FRAME,TRACKS,t=1.)
    votes.observe_many(FRAME,np.empty((0,5)),t=1.4)
    votes.observe_many(FRAME,TRACKS,t=1.6)
    assert votes.votes[430]=={'B':2}
    assert votes.last_resets==[]


@pytest.mark.parametrize('guarded',[False,True])
def test_backward_clock_clears_all_id_and_policy_state_even_on_empty_frame(monkeypatch, guarded):
    votes,_=voter(monkeypatch,guarded)
    for t in [10.,10.2,10.4]:votes.observe_many(FRAME,TRACKS,t=t)
    assert votes.label(430)=='B'
    votes.observe_many(FRAME,np.empty((0,5)),t=0.)
    assert votes.votes=={} and votes.last_seen=={} and votes.guarded_labels=={}
    if votes.policy:assert votes.policy.rows=={}
    assert votes.last_resets==[{'reason':'clock_reversed','time':0.}]


def test_explicit_reset_clears_stream_time_and_invalid_time_is_rejected(monkeypatch):
    votes,_=voter(monkeypatch)
    votes.observe(430,FRAME,TRACKS[0,:4],t=10.)
    votes.reset()
    assert votes.last_time is None and votes.last_seen=={}
    with pytest.raises(ValueError,match='Finite'):
        votes.observe_many(FRAME,TRACKS,t=float('nan'))
