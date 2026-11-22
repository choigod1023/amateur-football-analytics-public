import numpy as np
from scripts.audit_team_vote_confidence import WindowVote, confident

def test_low_margin_and_uncertain_votes_are_withheld():
    assert not confident(np.array([.1,.1,.39,.41]))
    assert confident(np.array([.05,.05,.1,.8]))
    v=WindowVote()
    assert v.update(1,'A') is None
    assert v.update(1,'A') is None
    assert v.update(1,'A')=='A'
    assert v.update(1,None) is None
    for _ in range(15):result=v.update(1,None)
    assert result is None

def test_old_team_does_not_vote_forever():
    v=WindowVote()
    for _ in range(30):v.update(1,'A')
    for _ in range(15):result=v.update(1,'B')
    assert result=='B'
    assert v.update(2,'B') is None

def test_referee_evidence_does_not_become_a_team():
    v=WindowVote()
    for _ in range(15):v.update(1,'A')
    assert v.update(1,'R') is None
    for _ in range(15):assert v.update(1,'R') is None

def test_non_finite_probabilities_are_not_confident():
    assert not confident([float('nan'),.9])

def test_live_guard_abstains_on_current_uncertainty_and_resets(monkeypatch):
    from scripts import run_live_feedback_identity as live
    monkeypatch.setattr(live,'load_model',lambda _: {'classes':['team_a','team_b']})
    probabilities=[.9,.1]
    monkeypatch.setattr(live,'predict',lambda m,x:np.tile(probabilities,(len(x),1)))
    votes=live.TeamVotes('fake',guarded=True)
    frame=np.zeros((100,100,3),dtype=np.uint8)
    row=np.array([[10,10,20,40,1]])
    for _ in range(3):votes.observe_many(frame,row)
    assert votes.label(1)=='A'
    probabilities[:]=[.51,.49]
    votes.observe_many(frame,row)
    assert votes.label(1) is None
    votes.reset()
    assert not votes.policy.rows and not votes.votes and votes.label(1) is None
    votes.observe_many(frame,np.empty((0,5)))
    assert votes.last_decisions==[]
