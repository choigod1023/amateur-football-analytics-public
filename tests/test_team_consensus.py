import pytest
from app.team_consensus import TeamConsensus
from app.main import validate_config


def player(team='home', pid='1'):
    return {'id': pid, 'team': team, 'x': .2, 'y': .3}


def test_three_observations_conflict_unknown_and_identity_loss():
    c = TeamConsensus()
    assert c.update([player()], 1)[0]['team'] == 'unknown'
    assert c.update([player()], 1.1)[0]['team'] == 'unknown'
    assert c.update([player()], 1.2)[0]['team'] == 'home'
    assert c.update([player('unknown')], 1.3)[0]['team'] == 'unknown'
    assert c.update([player()], 1.4)[0]['team'] == 'unknown'
    assert c.update([player('away')], 1.5)[0]['team'] == 'unknown'
    assert c.update([], 1.6) == []
    assert c.update([player('away')], 1.7)[0]['team'] == 'unknown'


def test_gap_duplicate_reset_and_invalid_time():
    c = TeamConsensus()
    for t in (1., 1.1, 1.2):
        result = c.update([player()], t)
    assert result[0]['team'] == 'home'
    assert c.update([player()], 3)[0]['team'] == 'unknown'
    assert all(p['team'] == 'unknown' for p in c.update([player(), player()], 3.1))
    assert c.update([player()], 3.2)[0]['team'] == 'unknown'
    assert c.update([player()], 3.2)[0]['team'] == 'unknown'
    assert c.update([player()], float('nan'))[0]['team'] == 'unknown'
    c.reset()
    assert c.update([player()], 4)[0]['team'] == 'unknown'
    validate_config({'temporal_team_consensus': True})
    with pytest.raises(ValueError):
        validate_config({'temporal_team_consensus': 'true'})
