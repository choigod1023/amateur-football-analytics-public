import json

from fastapi.testclient import TestClient

from app.review_public import create_app


def make_store(tmp_path):
    clip = tmp_path / 'ball' / 'clips' / 'b01'
    clip.mkdir(parents=True)
    (clip / 'candidates.json').write_text(json.dumps(
        {'id': 'b01', 'camera': 'cam1', 'start': 100, 'fps': 5,
         'frames': [{'file': 'f_001.jpg', 'cands': []}, {'file': 'f_002.jpg', 'cands': []}, {'file': 'f_003.jpg', 'cands': []}]}),
        encoding='utf-8')
    (tmp_path / 'ball' / 'index.json').write_text(json.dumps({'clips': [{'id': 'b01'}]}), encoding='utf-8')
    return TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test'), {'Origin': 'http://example.test'}


def test_label_source_is_recorded_and_unknown_sources_are_refused(tmp_path):
    client, headers = make_store(tmp_path)
    save = '/api/v1/ball/label'
    saved = client.post(save, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'state': 'ball', 'x': 100.0,
                                                      'y': 200.0, 'source': 'suggestion'}).json()['saved']
    assert saved['source'] == 'suggestion' and 'verified' not in saved
    bad = {'clip': 'b01', 'frame': 'f_002.jpg', 'state': 'ball', 'x': 5.0, 'y': 6.0, 'source': 'whatever'}
    assert client.post(save, headers=headers, json=bad).status_code == 422


def test_positions_can_be_verified_and_the_old_position_is_kept(tmp_path):
    client, headers = make_store(tmp_path)
    save, verify = '/api/v1/ball/label', '/api/v1/ball/verify'
    client.post(save, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'state': 'ball', 'x': 100.0, 'y': 200.0, 'source': 'suggestion'})
    client.post(save, headers=headers, json={'clip': 'b01', 'frame': 'f_002.jpg', 'state': 'ball', 'x': 300.0, 'y': 310.0, 'source': 'manual'})
    client.post(save, headers=headers, json={'clip': 'b01', 'frame': 'f_003.jpg', 'state': 'none'})
    assert client.post(verify, json={'clip': 'b01', 'frame': 'f_001.jpg', 'verdict': 'ok'}).status_code == 403
    assert client.post(verify, headers=headers, json={'clip': 'b01', 'frame': 'f_003.jpg', 'verdict': 'ok'}).status_code == 409
    assert client.post(verify, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'verdict': 'moved'}).status_code == 409
    assert client.post(verify, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'verdict': 'maybe'}).status_code == 422
    assert client.post(verify, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'verdict': 'ok'}).json()['saved']['verified'] == 'ok'
    moved = client.post(verify, headers=headers, json={'clip': 'b01', 'frame': 'f_002.jpg', 'verdict': 'moved', 'x': 310.5, 'y': 305.0}).json()['saved']
    assert (moved['x'], moved['y'], moved['source'], moved['verified']) == (310.5, 305.0, 'verify_click', 'moved')
    assert [(h['x'], h['y'], h['source']) for h in moved['history']] == [(300.0, 310.0, 'manual')]
    counts = client.post('/api/v1/ball/list', headers=headers).json()['clips'][0]
    assert (counts['ball'], counts['none'], counts['verified_ok'], counts['verified_moved'],
            counts['verified_rejected'], counts['unverified']) == (2, 1, 1, 1, 0, 0)
    client.post(verify, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'verdict': 'rejected'})
    labels = client.post('/api/v1/ball/clip', headers=headers, json={'id': 'b01'}).json()['labels']
    assert labels['f_001.jpg']['verified'] == 'rejected' and labels['f_001.jpg']['state'] == 'ball'
    # saving the frame again starts a fresh, unverified record
    client.post(save, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'state': 'ball', 'x': 101.0, 'y': 201.0, 'source': 'tile'})
    fresh = client.post('/api/v1/ball/clip', headers=headers, json={'id': 'b01'}).json()['labels']['f_001.jpg']
    assert 'verified' not in fresh and fresh['source'] == 'tile'


def test_model_picks_prepared_offline_reach_the_page_but_are_not_labels(tmp_path):
    from app.ball_review import BallReview
    clip = tmp_path / 'ball' / 'clips' / 'b01'
    clip.mkdir(parents=True)
    (clip / 'candidates.json').write_text(json.dumps({'id': 'b01', 'camera': 'cam1', 'start': 1, 'fps': 5, 'frames': [{'file': 'f_001.jpg', 'cands': [[10, 20, 0.5]], 'pick': [10.0, 20.0, 0.8]}]}), encoding='utf-8')
    data = BallReview(tmp_path).clip('b01')
    assert data['frames'][0]['pick'] == [10.0, 20.0, 0.8] and data['labels'] == {}
