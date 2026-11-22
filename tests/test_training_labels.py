import json
import numpy as np
from fastapi.testclient import TestClient
from app import main
from app.training_labels import TrainingLabels


def test_snapshot_label_saved_with_same_frame_and_role(tmp_path, monkeypatch):
    store = TrainingLabels(tmp_path)
    frame = np.full((80, 120, 3), 127, dtype=np.uint8)
    store.publish(frame, [(np.array([12, 8, 60, 72]), 17)], '2026-11-11T00:00:00Z', 'live', {'17': 0})
    monkeypatch.setattr(main, 'training_labels', store)
    client = TestClient(main.app, client=('127.0.0.1', 1234), base_url='http://127.0.0.1:8000')
    origin = {'Origin': 'http://127.0.0.1:8000'}
    assert client.post('/api/v1/training-labels/snapshot').status_code == 403
    snap = client.post('/api/v1/training-labels/snapshot', headers=origin).json()
    assert (tmp_path / 'pending' / (snap['token'] + '.jpg')).exists()
    monkeypatch.setattr(main, 'training_labels', TrainingLabels(tmp_path))
    assert client.post('/api/v1/training-labels/restore', json={'token': snap['token']}, headers=origin).json()['people'] == snap['people']
    body = {'token':snap['token'], 'track_id':'17', 'role':'goalkeeper', 'team_group':'white', 'shirt_color':'yellow'}
    saved = client.post('/api/v1/training-labels', json=body, headers=origin)
    assert saved.status_code == 200
    label = json.loads((tmp_path / (saved.json()['id'] + '.json')).read_text(encoding='utf-8'))
    assert label['captured_at'] == '2026-11-11T00:00:00Z'
    assert label['bbox_image_norm'] == [0.1, 0.1, 0.5, 0.9]
    assert label['role'] == 'goalkeeper' and label['team'] == 'unknown'
    assert label['team_group'] == 'white' and label['shirt_color'] == 'yellow'
    assert label['suggested_color_group_unverified'] == 0
    assert (tmp_path / label['image']).is_file()
    assert 'Not a complete annotation' in label['note']
    body['track_id'] = '18'
    assert client.post('/api/v1/training-labels', json=body, headers=origin).status_code == 409


def test_refuses_remote_and_invalid_team(tmp_path, monkeypatch):
    store = TrainingLabels(tmp_path)
    store.publish(np.zeros((40, 40, 3), dtype=np.uint8), [(np.array([1,1,20,20]), 'x')], 'now', 'file')
    monkeypatch.setattr(main, 'training_labels', store)
    remote = TestClient(main.app, client=('192.0.2.1', 9), base_url='http://example.test')
    assert remote.post('/api/v1/training-labels/snapshot', headers={'Origin':'http://example.test'}).status_code == 403
    local = TestClient(main.app, client=('127.0.0.1', 9), base_url='http://localhost')
    headers = {'Origin':'http://localhost'}
    token = local.post('/api/v1/training-labels/snapshot', headers=headers).json()['token']
    assert local.post('/api/v1/training-labels', headers=headers, json={'token':token,'track_id':'x','role':'referee','team_group':'white','shirt_color':'unknown'}).status_code == 422


def test_manual_box_and_negative_roles_are_persistent_and_separate(tmp_path, monkeypatch):
    store = TrainingLabels(tmp_path)
    store.publish(np.zeros((100, 100, 3), dtype=np.uint8), [(np.array([5, 5, 20, 50]), 'old')], 'now', 'own_recording', provenance={'split':'unassigned'})
    monkeypatch.setattr(main, 'training_labels', store)
    c = TestClient(main.app, client=('127.0.0.1', 1), base_url='http://localhost')
    h = {'Origin':'http://localhost'}
    token = c.post('/api/v1/training-labels/snapshot', headers=h).json()['token']
    original = c.post('/api/v1/training-labels', headers=h, json={'token':token,'track_id':'old','role':'player','team_group':'white','shirt_color':'white'}).json()['id']
    original_bytes = (tmp_path / (original + '.json')).read_bytes()
    assert c.post('/api/v1/training-labels/manual-box', json={'token':token,'bbox':[.2,.2,.4,.7]}).status_code == 403
    added = c.post('/api/v1/training-labels/manual-box', headers=h, json={'token':token,'bbox':[.2,.2,.4,.7]})
    assert added.status_code == 200
    person = added.json()['person']
    assert person['id'].startswith('manual-') and person['bbox'] == [.2,.2,.4,.7]
    monkeypatch.setattr(main, 'training_labels', TrainingLabels(tmp_path))
    restored = c.post('/api/v1/training-labels/restore', headers=h, json={'token':token}).json()
    assert [p['id'] for p in restored['people']] == ['old', person['id']]
    for role, expected in [('spectator','person_outside_play'),('shadow','background_negative'),('duplicate','duplicate_box')]:
        body={'token':token,'track_id':person['id'],'role':role,'team_group':'white','shirt_color':'unknown'}
        assert c.post('/api/v1/training-labels', headers=h, json=body).status_code == 422
        body['team_group']='unknown'
        response=c.post('/api/v1/training-labels', headers=h, json=body)
        assert response.status_code == 200
        data=json.loads((tmp_path / (response.json()['id'] + '.json')).read_text(encoding='utf-8'))
        assert data['training_disposition']==expected and data['annotation_origin']=='human_drawn'
        assert data['source_provenance']['split']=='unassigned'
    assert (tmp_path / (original + '.json')).read_bytes() == original_bytes
    for box in [[.2,.2,.2,.7],[-.1,.2,.3,.7],[.2,.2,1.1,.7],[.2,.2,.3]]:
        assert c.post('/api/v1/training-labels/manual-box', headers=h, json={'token':token,'bbox':box}).status_code in (409,422)
