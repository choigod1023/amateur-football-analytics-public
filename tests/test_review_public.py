import json

import numpy as np
from fastapi.testclient import TestClient

from app.review_public import create_app
from app.training_labels import TrainingLabels


def test_public_review_manual_box_and_distinct_false_positive_labels(tmp_path):
    original = TrainingLabels(tmp_path)
    original.publish(np.zeros((100,100,3), dtype=np.uint8), [([10,10,25,50], '1')], 'time', 'user_recording')
    token = original.freeze()['token']
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    headers = {'Origin': 'http://example.test'}
    assert client.post('/api/v1/training-labels/latest', headers=headers).json()['token'] == token
    assert client.post('/api/v1/training-labels/manual-box', json={'token':token, 'bbox':[.4,.1,.6,.8]}).status_code == 403
    result = client.post('/api/v1/training-labels/manual-box', headers=headers,
                         json={'token':token, 'bbox':[.4,.1,.6,.8]})
    assert result.status_code == 200
    ident = result.json()['person']['id']
    assert ident.startswith('manual-')
    payload = {'token':token, 'track_id':ident, 'role':'spectator', 'team_group':'unknown', 'shirt_color':'unknown'}
    answer = client.post('/api/v1/training-labels', headers=headers, json=payload)
    assert answer.status_code == 200
    stored = json.loads((tmp_path / (answer.json()['id'] + '.json')).read_text(encoding='utf-8'))
    assert stored['training_disposition'] == 'person_outside_play'
    assert stored['annotation_origin'] == 'human_drawn'
    assert len(client.post('/api/v1/training-labels/restore', headers=headers, json={'token':token}).json()['people']) == 2
    payload.update(role='shadow', team_group='team_a')
    assert client.post('/api/v1/training-labels', headers=headers, json=payload).status_code == 422


def test_service_rejects_wrong_host_and_only_serves_expected_files(tmp_path):
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    assert client.get('/train').status_code == 200
    assert client.get('/review-annotation.js').status_code == 200
    assert client.get('/unknown').status_code == 404
    assert client.get('/train', headers={'Host':'other.test'}).status_code == 403


def test_scene_queue_is_ordered_and_skips_broken_scenes(tmp_path):
    pending = tmp_path / 'pending'
    pending.mkdir()
    for token, order in (('b' * 32, 20), ('a' * 32, 10), ('c' * 32, 30)):
        (pending / (token + '.jpg')).write_bytes(b'jpeg')
        (pending / (token + '.json')).write_text(
            json.dumps({'people': [], 'timestamp': order, 'source': 'unit', 'order': order}), encoding='utf-8')
    (pending / ('d' * 32 + '.json')).write_text('{broken', encoding='utf-8')
    (pending / ('e' * 32 + '.json')).write_text(json.dumps({'people': []}), encoding='utf-8')
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    headers = {'Origin': 'http://example.test'}
    assert client.post('/api/v1/training-labels/scenes').status_code == 403
    scenes = client.post('/api/v1/training-labels/scenes', headers=headers).json()['scenes']
    assert [s['token'] for s in scenes] == ['a' * 32, 'b' * 32, 'c' * 32]
    assert all(s['box_count'] == 0 for s in scenes)


def test_pitch_region_is_validated_stored_and_clearable(tmp_path):
    pending = tmp_path / 'pending'
    pending.mkdir()
    token = 'a' * 32
    (pending / (token + '.jpg')).write_bytes(b'jpeg')
    (pending / (token + '.json')).write_text(json.dumps(
        {'people': [], 'timestamp': 't', 'source': 'unit',
         'source_provenance': {'split': 'eval', 'clip_time_sec': 90.0}}), encoding='utf-8')
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    headers = {'Origin': 'http://example.test'}
    url = '/api/v1/training-labels/pitch-region'
    square = [[.1, .5], [.9, .5], [.9, .9], [.1, .9]]
    assert client.post(url, json={'token': token, 'polygon': square}).status_code == 403
    assert client.post(url, headers=headers, json={'token': token, 'polygon': square[:2]}).status_code == 409
    assert client.post(url, headers=headers, json={'token': token, 'polygon': [[0, 0], [.01, 0], [0, .01]]}).status_code == 409
    assert client.post(url, headers=headers, json={'token': token, 'polygon': [[0, 0], [2, 0], [0, .5]]}).status_code == 409
    assert client.post(url, headers=headers, json={'token': 'b' * 32, 'polygon': square}).status_code == 409
    saved = client.post(url, headers=headers, json={'token': token, 'polygon': square}).json()['regions']
    assert saved == {token: square}
    assert client.post('/api/v1/training-labels/pitch-regions', headers=headers).json()['regions'] == saved
    scene = client.post('/api/v1/training-labels/scenes', headers=headers).json()['scenes'][0]
    assert scene['split'] == 'eval' and scene['clip_time'] == 90.0
    assert client.post(url, headers=headers, json={'token': token, 'polygon': []}).json()['regions'] == {}


def test_calibration_scene_labels_and_camera_fields(tmp_path):
    pending = tmp_path / 'pending'
    pending.mkdir()
    token = 'c' * 32
    (pending / (token + '.jpg')).write_bytes(b'jpeg')
    (pending / (token + '.json')).write_text(json.dumps(
        {'people': [], 'timestamp': 't', 'source': 'unit',
         'source_provenance': {'split': 'train', 'clip_time_sec': 30.0, 'camera_setting': 'cam1',
                               'bg_to_ref': [1.0, 0.0, 2.5, -1.0]}}), encoding='utf-8')
    (tmp_path / ('d' * 32 + '.json')).write_text(json.dumps(
        {'image': token + '.jpg', 'track_id': 'cand-01', 'role': 'player', 'team_group': 'team_a',
         'bbox_image_norm': [.1, .2, .2, .5], 'annotation_origin': 'model_candidate'}), encoding='utf-8')
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    headers = {'Origin': 'http://example.test'}
    scene = client.post('/api/v1/training-labels/scenes', headers=headers).json()['scenes'][0]
    assert scene['camera'] == 'cam1' and scene['bg'] == [1.0, 0.0, 2.5, -1.0] and scene['split'] == 'train'
    labels = client.post('/api/v1/training-labels/scene-labels', headers=headers, json={'token': token}).json()['labels']
    assert labels == [{'track_id': 'cand-01', 'role': 'player', 'team_group': 'team_a', 'bbox': [.1, .2, .2, .5], 'origin': 'model_candidate'}]
    pitch = {'length': 90, 'width': 55, 'circle_r': 9.15, 'goal_width': 7.32, 'pa_depth': 16.5, 'pa_width': 40.3, 'ga_depth': 5.5, 'ga_width': 18.3}
    pts = [{'landmark': n, 'x': x, 'y': y} for n, x, y in
           (('center', .5, .6), ('half_near', .5, .9), ('half_far', .5, .5), ('circle_left', .4, .6))]
    url = '/api/v1/training-labels/calibration'
    body = {'setting': 'cam1', 'points': pts, 'pitch': pitch, 'ref_token': token}
    assert client.post(url, json=body).status_code == 403
    assert client.post(url, headers=headers, json={**body, 'points': pts[:3]}).status_code == 409
    assert client.post(url, headers=headers, json={**body, 'points': pts[:3] + [{'landmark': 'nope', 'x': .1, 'y': .1}]}).status_code in (409, 422)
    assert client.post(url, headers=headers, json={**body, 'pitch': {**pitch, 'length': 5}}).status_code == 409
    assert client.post(url, headers=headers, json={**body, 'setting': 'camera1'}).status_code == 422
    saved = client.post(url, headers=headers, json=body).json()['calibrations']
    assert len(saved['cam1']['points']) == 4 and saved['cam1']['pitch_dimensions_are_estimates'] is True
    assert client.post('/api/v1/training-labels/calibrations', headers=headers).json()['calibrations'] == saved
    assert client.post(url, headers=headers, json={**body, 'points': []}).json()['calibrations'] == {}
    # the cleared record is kept in a history file so that an accidental clear can be undone by hand
    history = [json.loads(line) for line in (tmp_path / 'calibration' / 'calibration_history.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [h['setting'] for h in history] == ['cam1'] and len(history[0]['record']['points']) == 4


def test_scene_thumbnails_and_label_counts(tmp_path):
    import cv2
    pending = tmp_path / 'pending'
    pending.mkdir()
    token = 'e' * 32
    cv2.imwrite(str(pending / (token + '.jpg')), np.full((108, 192, 3), 90, dtype=np.uint8))
    (pending / (token + '.json')).write_text(json.dumps({'people': [], 'timestamp': 't', 'source': 'unit'}), encoding='utf-8')
    for i in range(3):
        (tmp_path / (str(i) * 32 + '.json')).write_text(json.dumps(
            {'image': token + '.jpg', 'track_id': f'cand-{i}', 'role': 'spectator', 'team_group': 'unknown',
             'bbox_image_norm': [.1, .2, .2, .5]}), encoding='utf-8')
    (tmp_path / ('9' * 32 + '.json')).write_text('{broken', encoding='utf-8')
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    headers = {'Origin': 'http://example.test'}
    scene = client.post('/api/v1/training-labels/scenes', headers=headers).json()['scenes'][0]
    assert scene['label_count'] == 3
    ok = client.get(f'/thumbs/{token}.jpg')
    assert ok.status_code == 200 and ok.headers['content-type'] == 'image/jpeg' and 'max-age' in ok.headers['cache-control']
    assert (tmp_path / 'thumbs' / (token + '.jpg')).is_file()
    assert client.get('/thumbs/' + 'f' * 32 + '.jpg').status_code == 404
    assert client.get('/thumbs/..%2Fpending%2F' + token + '.jpg').status_code == 404
    assert client.get('/thumbs/not-a-token.jpg').status_code == 404
    assert client.get('/train').headers['cache-control'] == 'no-store'


def test_event_review_lists_labels_and_serves_media(tmp_path):
    events = tmp_path / 'events'
    (events / 'media').mkdir(parents=True)
    (events / 'media' / 'c001.mp4').write_bytes(b'\x00\x00\x00\x18ftypmp42')
    (events / 'media' / 'c001.jpg').write_bytes(b'jpeg')
    (events / 'candidates.json').write_text(json.dumps(
        {'time_basis': 'clip seconds', 'method': 'heuristic', 'items': [
            {'id': 'c001', 't': 14.0, 'start': 0.0, 'end': 22.0, 'reasons': ['r1'], 'score': .9},
            {'id': 'bad', 't': 1}]}), encoding='utf-8')
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    headers = {'Origin': 'http://example.test'}
    listing = client.post('/api/v1/events/list', headers=headers).json()
    assert [c['id'] for c in listing['candidates']] == ['c001'] and listing['candidates'][0]['label'] is None
    assert client.post('/api/v1/events/list').status_code == 403
    url = '/api/v1/events/label'
    assert client.post(url, headers=headers, json={'id': 'c001', 'label': 'goal', 'event_time': 12.5, 'note': 'left goal'}).json()['saved']['label'] == 'goal'
    assert client.post(url, headers=headers, json={'id': 'c999', 'label': 'goal'}).status_code == 409
    assert client.post(url, headers=headers, json={'id': 'c001', 'label': 'nonsense'}).status_code == 422
    assert client.post(url, headers=headers, json={'id': '../x', 'label': 'goal'}).status_code == 422
    assert client.post(url, headers=headers, json={'id': 'c001', 'label': 'goal', 'event_time': -1}).status_code == 409
    after = client.post('/api/v1/events/list', headers=headers).json()
    assert after['candidates'][0]['label']['event_time'] == 12.5
    manual = client.post('/api/v1/events/manual', headers=headers, json={'time': 905.0, 'label': 'goal'}).json()['saved']
    assert manual['manual'] is True and manual['id'].startswith('m')
    assert client.post('/api/v1/events/manual', headers=headers, json={'time': 1.0, 'label': 'none'}).status_code == 422
    assert [m['id'] for m in client.post('/api/v1/events/list', headers=headers).json()['manual']] == [manual['id']]
    assert client.post(url, headers=headers, json={'id': manual['id'], 'label': 'clear'}).json()['saved'] is None
    assert client.post('/api/v1/events/list', headers=headers).json()['manual'] == []
    assert client.post(url, headers=headers, json={'id': 'c001', 'label': 'clear'}).json()['saved'] is None
    assert client.post('/api/v1/events/list', headers=headers).json()['candidates'][0]['label'] is None
    media = client.get('/event-media/c001.mp4')
    assert media.status_code == 200 and media.headers['content-type'] == 'video/mp4'
    assert client.get('/event-media/c001.jpg').headers['content-type'] == 'image/jpeg'
    assert client.get('/event-media/c002.mp4').status_code == 404
    assert client.get('/event-media/..%2Fcandidates.json').status_code == 404


def test_hand_drawn_box_can_be_deleted_only_while_unanswered(tmp_path):
    original = TrainingLabels(tmp_path)
    original.publish(np.zeros((100, 100, 3), dtype=np.uint8), [([10, 10, 25, 50], '1')], 'time', 'user_recording')
    token = original.freeze()['token']
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    headers = {'Origin': 'http://example.test'}
    first = client.post('/api/v1/training-labels/manual-box', headers=headers, json={'token': token, 'bbox': [.4, .1, .6, .8]}).json()['person']['id']
    second = client.post('/api/v1/training-labels/manual-box', headers=headers, json={'token': token, 'bbox': [.1, .1, .2, .2]}).json()['person']['id']
    url = '/api/v1/training-labels/delete-box'
    assert client.post(url, json={'token': token, 'id': first}).status_code == 403
    assert client.post(url, headers=headers, json={'token': token, 'id': '1'}).status_code == 422
    assert client.post(url, headers=headers, json={'token': token, 'id': 'manual-0000000000000000'}).status_code == 409
    answered = {'token': token, 'track_id': second, 'role': 'player', 'team_group': 'team_a', 'shirt_color': 'unknown'}
    assert client.post('/api/v1/training-labels', headers=headers, json=answered).status_code == 200
    assert client.post(url, headers=headers, json={'token': token, 'id': second}).status_code == 409
    assert client.post(url, headers=headers, json={'token': token, 'id': first}).json() == {'remaining': 2}
    people = client.post('/api/v1/training-labels/restore', headers=headers, json={'token': token}).json()['people']
    assert [p['id'] for p in people] == ['1', second]
    on_disk = json.loads((tmp_path / 'pending' / (token + '.json')).read_text(encoding='utf-8'))
    assert [p['id'] for p in on_disk['people']] == ['1', second]


def test_ball_review_lists_clips_and_saves_only_valid_positions(tmp_path):
    clip = tmp_path / 'ball' / 'clips' / 'b01'
    clip.mkdir(parents=True)
    (clip / 'f_001.jpg').write_bytes(b'jpeg')
    (clip / 'candidates.json').write_text(json.dumps(
        {'id': 'b01', 'camera': 'cam1', 'start': 100, 'fps': 5,
         'frames': [{'file': 'f_001.jpg', 'cands': [[900.0, 800.0, .5]]}, {'file': 'f_002.jpg', 'cands': []}]}), encoding='utf-8')
    (tmp_path / 'ball' / 'index.json').write_text(json.dumps({'clips': [{'id': 'b01'}, {'id': 'b02'}], 'note': 'n'}), encoding='utf-8')
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    headers = {'Origin': 'http://example.test'}
    listing = client.post('/api/v1/ball/list', headers=headers).json()
    assert [c['id'] for c in listing['clips']] == ['b01'] and listing['clips'][0]['frames'] == 2
    assert client.post('/api/v1/ball/clip', headers=headers, json={'id': 'b09'}).status_code == 404
    data = client.post('/api/v1/ball/clip', headers=headers, json={'id': 'b01'}).json()
    assert data['frames'][0]['cands'] == [[900.0, 800.0, .5]] and data['labels'] == {}
    url = '/api/v1/ball/label'
    assert client.post(url, json={'clip': 'b01', 'frame': 'f_001.jpg', 'state': 'none'}).status_code == 403
    assert client.post(url, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'state': 'ball', 'x': 2500.0, 'y': 5.0}).status_code == 409
    assert client.post(url, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'state': 'ball'}).status_code == 409
    assert client.post(url, headers=headers, json={'clip': 'b01', 'frame': 'f_009.jpg', 'state': 'none'}).status_code == 409
    assert client.post(url, headers=headers, json={'clip': 'b01', 'frame': '../x', 'state': 'none'}).status_code == 422
    saved = client.post(url, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'state': 'ball', 'x': 911.2, 'y': 813.4}).json()['saved']
    assert saved['x'] == 911.2 and saved['state'] == 'ball'
    assert client.post(url, headers=headers, json={'clip': 'b01', 'frame': 'f_002.jpg', 'state': 'unsure'}).json()['saved']['state'] == 'unsure'
    after = client.post('/api/v1/ball/list', headers=headers).json()['clips'][0]
    assert (after['labeled'], after['ball'], after['unsure']) == (2, 1, 1)
    assert client.post(url, headers=headers, json={'clip': 'b01', 'frame': 'f_001.jpg', 'state': 'clear'}).json()['saved'] is None
    assert client.post('/api/v1/ball/clip', headers=headers, json={'id': 'b01'}).json()['labels'].keys() == {'f_002.jpg'}
    assert client.get('/ball-media/b01/f_001.jpg').status_code == 200
    assert client.get('/ball-media/b01/f_002.jpg').status_code == 404
    assert client.get('/ball-media/b01/..%2Fcandidates.json').status_code == 404
