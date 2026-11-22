from app.live_publish import dashboard_players
from app.live_publish import LivePublisher
import numpy as np
import json
from pathlib import Path
import pytest


def test_snapshot_survives_temporary_reader_lock(tmp_path, monkeypatch):
    from app import live_publish
    target = tmp_path / 'snapshot.json'
    target.write_text('{"old": true}', encoding='utf-8')
    original = Path.replace
    attempts = []
    def locked_replace(source, destination):
        attempts.append(1)
        if len(attempts) <= 3:
            assert json.loads(target.read_text()) == {'old': True}
            raise PermissionError('reader holds Windows delete-sharing lock')
        return original(source, destination)
    monkeypatch.setattr(Path, 'replace', locked_replace)
    monkeypatch.setattr(live_publish.time, 'sleep', lambda _: None)
    LivePublisher(tmp_path).publish(np.zeros((20,20,3), dtype=np.uint8), [], [],
        7, {'length':89,'width':60}, True, 5, 200)
    snapshot = json.loads(target.read_text(encoding='utf-8'))
    assert snapshot['analysis']['source_time_s'] == 7
    assert (tmp_path / snapshot['frame_file']).is_file()
    assert len(attempts) == 4


def test_persistent_snapshot_lock_is_bounded_and_preserves_old_file(tmp_path, monkeypatch):
    from app import live_publish
    target = tmp_path / 'snapshot.json'
    target.write_text('{"old": true}', encoding='utf-8')
    attempts = []
    def locked_replace(source, destination):
        attempts.append(1)
        raise PermissionError('persistent permission failure')
    monkeypatch.setattr(Path, 'replace', locked_replace)
    monkeypatch.setattr(live_publish.time, 'sleep', lambda _: None)
    with pytest.raises(PermissionError):
        LivePublisher(tmp_path).publish(np.zeros((20,20,3), dtype=np.uint8), [], [],
            7, {'length':89,'width':60}, True, 5, 200)
    assert len(attempts) == 11
    assert json.loads(target.read_text()) == {'old': True}


def test_centre_and_corners_translate_without_clamping_off_pitch():
    rows = dashboard_players({'home': [(1, 0, 0), (2, -44.5, -30), (3, 44.5, 30), (4, 46, 0)]}, {'length':89, 'width':60})
    assert (rows[0]['x'], rows[0]['y']) == (.5,.5)
    assert (rows[1]['x'], rows[1]['y']) == (0,0)
    assert (rows[2]['x'], rows[2]['y']) == (1,1)
    assert rows[3]['x'] is None and rows[3]['y'] is None


def test_team_excess_blocks_metrics_and_feedback_without_hiding_evidence(tmp_path):
    players = dashboard_players({'home': [(i, i, 0) for i in range(12)]}, {'length':89, 'width':60})
    data = LivePublisher(tmp_path).publish(np.zeros((20,20,3), dtype=np.uint8), players,
        [{'title':'candidate','text':'candidate'}], 1, {'length':89,'width':60}, True, 5, 200)
    assert len(data['players']) == 12
    assert data['feedback'] == []
    assert data['metrics']['team_width_m'] is None
    assert data['coaching_diagnostics']['state'] == 'blocked'


def test_filtered_display_does_not_change_metric_input(tmp_path):
    raw=dashboard_players({'home':[(1,0,0),(2,1,1),(3,2,2)]},{'length':89,'width':60})
    display=dashboard_players({'home':[(1,0,0),(2,1,1),(3,2.5,2.5)]},{'length':89,'width':60})
    data=LivePublisher(tmp_path).publish(np.zeros((20,20,3),dtype=np.uint8),display,[],0,
        {'length':89,'width':60},True,5,200,raw_players=raw)
    assert abs(data['metrics']['team_width_m']-2)<1e-9
    assert data['players']==display and data['raw_players']==raw


def test_display_omission_cannot_hide_raw_over_capacity(tmp_path):
    raw=dashboard_players({'home':[(i,i,0) for i in range(12)]},{'length':89,'width':60})
    data=LivePublisher(tmp_path).publish(np.zeros((20,20,3),dtype=np.uint8),raw[:11],[],0,
        {'length':89,'width':60},True,5,200,raw_players=raw)
    assert data['metrics']['team_width_m'] is None
    assert data['coaching_diagnostics']['state']=='blocked'
