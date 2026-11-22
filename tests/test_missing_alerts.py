from app.live_feedback import LiveAnalyzer


def people(front=30):
    return [(str(i), front-x, (i % 3)*2) for i,x in enumerate([0,20,23,26,29,32,35,38])]


def test_real_samples_survive_last_frame_dropout_without_inventing_positions():
    a = LiveAnalyzer(1)
    team, other = people(), people(20)
    for f in range(5):
        a.frames[f] = {'team': team if f<3 else [], 'other': other}
    a._close_second(0, [], other)
    assert 0 not in a.series['team']
    assert a.isolation_series[0]['observed_samples'] == 3
    assert a.isolation_series[0]['leader_isolation'] > 12
    assert a.frames[4]['team'] == []


def test_sparse_second_cannot_be_filled_or_carried_forward():
    a=LiveAnalyzer(1)
    for f in range(5):
        a.frames[f]={'team':people() if f<2 else [],'other':people(20)}
    a._close_second(0, [], people(20))
    assert 0 not in a.isolation_series


def test_informational_line_change_does_not_block_supported_isolation(monkeypatch):
    import app.live_feedback as module
    monkeypatch.setattr(module, 'smooth', lambda x: x)
    a=LiveAnalyzer(1, disabled=())      # isolated is off by default since 2026-11-20 (DISABLED_KINDS); the rule itself is tested here
    a.series['other']={0:{'opponent_back_line':0},1:{'opponent_back_line':20}}
    alerts=a._check(2,1)
    assert alerts[0]['kind']=='line_drop' and alerts[0]['polarity']=='info'
    assert a.last_alert['line_drop']==2 and a.last_any < 0
    a.isolation_series={s:{'centre':10,'leader_isolation':20,'observed_samples':3,'leader_ids':['x']} for s in range(6)}
    a.attack_detail=lambda: None
    alerts=a._check(6,5)
    assert any(e['kind']=='isolated' for e in alerts)
    assert alerts[0]['evidence']['same_player_continuity_verified'] is False
