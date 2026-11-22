import numpy as np
import pytest
from scripts import run_live_feedback_identity as live


@pytest.mark.parametrize('guarded',[False,True])
def test_crossing_cannot_transfer_old_team_votes(monkeypatch,guarded):
    monkeypatch.setattr(live,'load_model',lambda _: {'classes':['team_a','team_b']})
    probabilities=[.99,.01]
    monkeypatch.setattr(live,'predict',lambda m,x:np.tile(probabilities,(len(x),1)))
    frame=np.zeros((100,100,3),np.uint8)
    clean=np.array([[10,10,20,50,1],[60,10,70,50,2]])
    overlap=np.array([[30,10,40,50,1],[32,10,42,50,2]])
    votes=live.TeamVotes('test',guarded=guarded)
    for i in range(5):votes.observe_many(frame,clean,t=i*.2)
    assert votes.label(1)=='A'
    probabilities[:]=[.01,.99]
    votes.observe_many(frame,overlap,t=1.)
    assert not votes.votes and votes.label(1) is None
    assert all(e['reason']=='overlap_identity_uncertain' for e in votes.last_resets)
    for t in (1.2,1.4):
        votes.observe_many(frame,clean,t=t)
        assert votes.label(1) is None
    votes.observe_many(frame,clean,t=1.6)
    assert votes.label(1)=='B'  # three new clean crops, never inherited A history
    votes.reset();assert not votes.crowded_ids


def test_nonoverlapping_track_is_not_reset(monkeypatch):
    monkeypatch.setattr(live,'load_model',lambda _: {'classes':['team_a','team_b']})
    monkeypatch.setattr(live,'predict',lambda m,x:np.tile([.99,.01],(len(x),1)))
    v=live.TeamVotes('test');f=np.zeros((100,100,3),np.uint8)
    clear=np.array([[10,10,20,50,1],[60,10,70,50,2],[80,10,90,50,3]])
    for t in (0,.2,.4):v.observe_many(f,clear,t=t)
    clear[1,:4]=[12,10,22,50];v.observe_many(f,clear,t=.6)
    assert v.label(3)=='A' and v.votes[3]['A']==4
    assert v.label(1) is None
