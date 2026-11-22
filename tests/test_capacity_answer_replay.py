from scripts.audit_capacity_answer_replay import ReplayVotes


def test_long_gap_starts_new_votes_without_faking_confirmed_label():
    old,reset=ReplayVotes(),ReplayVotes(.6)
    for t in (0,.2,.4):
        assert old.update('1',t,'B')==reset.update('1',t,'B')
    assert old.update('1',10,'A')['team']=='B'
    assert reset.update('1',10,'A')['team'] is None
    assert reset.update('1',10.2,'A')['team'] is None
    assert reset.update('1',10.4,'A')['team']=='A'
    assert reset.resets==1


def test_role_exclusion_and_threshold_boundary_are_preserved():
    reset=ReplayVotes(.6)
    for t in (0,.6,1.2):result=reset.update('1',t,'S')
    assert reset.resets==0
    assert result['winner']=='S' and result['team'] is None
