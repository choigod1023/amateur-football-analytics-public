import time
import pytest
from fastapi import HTTPException
from app.manual_tracks import ManualTracks
import app.main as main
from fastapi.testclient import TestClient


def snapshot_for(registry, tid='1'):
    token, _, _ = registry.get(tid)
    registry.publish_snapshot(b'jpeg', [{'id':tid, 'team':'unknown', 'annotation_token':token}], 'frame-1')
    snapshot = registry.get_snapshot()
    return snapshot['snapshot_token'], token


def test_confirmation_needs_matching_snapshot_and_role_is_not_assumed():
    r=ManualTracks();r.observe(['1']);snapshot, token=snapshot_for(r)
    assert r.get('1')[1:] == ('unknown', None)
    assert not r.assign('forged', '1', token, 'player', 'home')
    assert not r.assign(snapshot, '1', 'forged', 'player', 'home')
    assert r.assign(snapshot, '1', token, 'player', 'home')
    assert r.get('1')[1:] == ('home', 'player')
    assert r.assign(snapshot, '1', token, 'referee', 'unknown')
    assert r.get('1')[1:] == ('unknown', 'referee')


def test_track_disappearance_duplicate_reappearance_and_reset_revoke_tokens():
    r=ManualTracks();r.observe(['1']);snapshot, old=snapshot_for(r)
    r.observe([]);r.observe(['1']);new=r.get('1')[0]
    assert new != old
    assert not r.assign(snapshot, '1', old, 'player', 'home')
    fresh, token=snapshot_for(r)
    r.observe(['1','1'])
    assert not r.assign(fresh, '1', token, 'player', 'home')
    r.observe(['1']);r.reset()
    assert r.get_snapshot() is None


def test_expiry_invalidates_both_snapshot_and_role(monkeypatch):
    clock=[10.]
    monkeypatch.setattr('app.manual_tracks.time.monotonic', lambda:clock[0])
    r=ManualTracks(ttl_s=10);r.observe(['1']);snap,token=snapshot_for(r)
    assert r.assign(snap,'1',token,'player','home')
    clock[0]=21.
    assert r.get('1')[1:] == ('unknown',None)
    assert r.get_snapshot() is None
    assert not r.assign(snap,'1',token,'player','home')


def test_longer_review_keeps_short_role_ttl_and_rejects_recycled_id(monkeypatch):
    clock = [10.]
    monkeypatch.setattr('app.manual_tracks.time.monotonic', lambda: clock[0])
    r = ManualTracks(ttl_s=10, snapshot_ttl_s=60)
    r.observe(['1'])
    snap, token = snapshot_for(r)
    clock[0] = 30.
    assert r.assign(snap, '1', token, 'goalkeeper', 'away')
    assert r.get('1')[1:] == ('away', 'goalkeeper')
    clock[0] = 41.
    assert r.get('1')[1:] == ('unknown', None)
    r.observe([])
    r.observe(['1'])
    assert not r.assign(snap, '1', token, 'player', 'home')


def test_only_requested_snapshots_are_retained_and_bounded():
    r = ManualTracks(snapshot_ttl_s=60)
    r.observe(['1'])
    token = r.get('1')[0]
    for _ in range(100):
        r.publish_snapshot(b'jpeg', [{'id':'1', 'annotation_token':token}], 'frame')
    assert not r.snapshots
    for _ in range(70):
        assert r.get_snapshot()
    assert len(r.snapshots) == 64


def test_api_refuses_stale_source_and_invalid_role_team(monkeypatch):
    monkeypatch.setattr(main, 'manual_mode', True)
    monkeypatch.setattr(main, 'last_analysis_monotonic', time.monotonic()-2)
    request=main.ManualTrackRequest(id='1',token='x',snapshot_token='x',role='player',team='home')
    with pytest.raises(HTTPException) as ex: main.assign_manual_track(request)
    assert ex.value.status_code == 409
    request=main.ManualTrackRequest(id='1',token='x',snapshot_token='x',role='referee',team='home')
    with pytest.raises(HTTPException) as ex: main.assign_manual_track(request)
    assert ex.value.status_code == 400


def test_http_confirmation_uses_snapshot_and_refuses_recycled_id(monkeypatch):
    registry=ManualTracks()
    registry.observe(['1'])
    snapshot, token=snapshot_for(registry)
    monkeypatch.setattr(main, 'manual_tracks', registry)
    monkeypatch.setattr(main, 'manual_mode', True)
    monkeypatch.setattr(main, 'last_analysis_monotonic', time.monotonic())
    monkeypatch.setattr(main, 'status', {'status':'running'})
    client=TestClient(main.app)
    frame=client.get('/api/v1/manual-snapshot')
    assert frame.status_code == 200
    assert frame.headers['cache-control'] == 'no-store'
    assert frame.json()['captured_at'] == 'frame-1'
    request={'id':'1','token':token,'snapshot_token':snapshot,'role':'player','team':'home'}
    assert client.post('/api/v1/manual-track',json=request).status_code == 200
    assert registry.get('1')[1:] == ('home','player')
    registry.observe([]);registry.observe(['1'])
    assert client.post('/api/v1/manual-track',json=request).status_code == 409


def test_confirmed_track_is_visible_immediately_without_reusing_old_metrics(monkeypatch):
    registry = ManualTracks()
    registry.observe(['1'])
    snapshot, token = snapshot_for(registry)
    monkeypatch.setattr(main, 'manual_tracks', registry)
    monkeypatch.setattr(main, 'manual_mode', True)
    monkeypatch.setattr(main, 'last_analysis_monotonic', time.monotonic())
    monkeypatch.setattr(main, 'status', {'status':'running'})
    monkeypatch.setattr(main, 'analysis', {'players':[{'id':'1', 'team':'unknown', 'role':None, 'annotation_token':token}],
        'metrics':{'team_width_m':5,'team_length_m':2}, 'feedback':[{}], 'movements':[], 'formation_changes':[]})
    client = TestClient(main.app)
    body = {'id':'1', 'token':token, 'snapshot_token':snapshot, 'role':'player', 'team':'home'}
    assert client.post('/api/v1/manual-track', json=body).status_code == 200
    result = client.get('/api/v1/analysis').json()
    assert result['players'][0]['team'] == 'home'
    assert result['players'][0]['role'] == 'player'
    assert result['metrics']['team_width_m'] is None and result['feedback'] == []
    assert result['coaching_diagnostics']['state'] == 'blocked'
    registry.observe([])
    registry.observe(['1'])
    result = client.get('/api/v1/analysis').json()
    assert result['players'][0]['team'] == 'unknown'
    assert result['players'][0]['role'] is None


def test_mode_switch_during_analysis_cannot_skip_old_confirmation_check(monkeypatch):
    registry=ManualTracks()
    monkeypatch.setattr(main, 'manual_tracks', registry)
    monkeypatch.setattr(main, 'manual_mode', True)
    monkeypatch.setattr(main, 'last_analysis_monotonic', 100.)
    monkeypatch.setattr(main, 'status', {'status':'running'})
    monkeypatch.setattr(main, 'analysis', {'players':[{'id':'1','team':'home','role':'player','annotation_token':'old'}],
        'metrics':{'team_width_m':1,'team_length_m':1},'feedback':[{}],'movements':[],'formation_changes':[]})
    def switch_mode():
        main.manual_mode=False
        return 100.
    monkeypatch.setattr(main.time, 'monotonic', switch_mode)
    result=main.get_analysis()
    assert result['players'][0]['team'] == 'unknown'
    assert result['metrics']['team_width_m'] is None and result['feedback'] == []
