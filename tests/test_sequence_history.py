import cv2
import numpy as np
import httpx
from fastapi.testclient import TestClient

from app import main, sequence_store, plaintext_demo
from app.sequence_history import SequenceHistory, read_verified_frame
from app.main import active_calibration


def make_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (160, 90))
    assert writer.isOpened()
    for index in range(30):
        writer.write(np.full((90, 160, 3), (index * 7, 40, 100), dtype=np.uint8))
    writer.release()


def frame_at(path, index):
    cap = cv2.VideoCapture(str(path)); assert cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read(); cap.release(); assert ok
    return frame


def test_history_guards_input_identity_and_unvalidated_data(tmp_path):
    source = tmp_path / 'source.mp4'; make_video(source)
    history = SequenceHistory(capacity=2)
    player = {'id': '1', 'team': 'home', 'x': .2, 'y': .3}
    metrics = {'team_width_m': 10., 'team_length_m': 5.}
    feedback = [{'observation': 'example'}]
    history.reset(source)
    assert history.add(source, 10, 10., frame_at(source, 10), [player], metrics, feedback, teams_validated=False, calibration_validated=False)
    assert not history.add(source, 11, 10., frame_at(source, 11), [player], metrics, feedback, teams_validated=True, calibration_validated=True)
    snap = history.find(source, .5, 1.5)
    assert snap['frame_index'] == 10 and snap['players'][0] == {'id': '1', 'team': 'unknown', 'x': None, 'y': None}
    assert snap['metrics']['team_width_m'] is None and snap['feedback'] == []
    assert read_verified_frame(source, snap) is not None
    snap['digest'] = 'wrong'
    assert read_verified_frame(source, snap) is None
    assert history.find(source, 1.1, 2.0) is None
    history.reset()
    assert history.find(source, .5, 1.5) is None


def test_resolution_mismatch_cannot_publish_stale_coordinates(tmp_path):
    source = tmp_path / 'source.mp4'; make_video(source)
    history = SequenceHistory(); history.reset(source)
    calibration = {'validated': True, 'image_size_px': [1920, 1080]}
    active, reason = active_calibration(calibration, frame_at(source, 10).shape)
    assert active is None and reason == 'resolution_mismatch'
    assert history.add(source, 10, 10., frame_at(source, 10),
                       [{'id':'1', 'team':'home', 'x':.2, 'y':.3}],
                       {'team_width_m':10., 'team_length_m':5.}, [{'observation':'x'}],
                       teams_validated=True, calibration_validated=(active or {}).get('validated') is True)
    snapshot = history.find(source, .5, 1.5)
    assert snapshot['players'][0]['x'] is None and snapshot['players'][0]['y'] is None
    assert snapshot['metrics']['team_width_m'] is None and snapshot['feedback'] == []


def test_real_clip_with_exact_snapshot_and_range(tmp_path, monkeypatch):
    try: sequence_store.find_ffmpeg()
    except sequence_store.SequenceError:
        import pytest; pytest.skip('FFmpeg unavailable')
    upload_dir = tmp_path / 'uploads'; upload_dir.mkdir()
    source = upload_dir / 'source.mp4'; make_video(source)
    monkeypatch.setattr(sequence_store, 'UPLOADS', upload_dir)
    monkeypatch.setattr(sequence_store, 'SEQUENCES', tmp_path / 'sequences')
    monkeypatch.setitem(main.status, 'source', str(source))
    monkeypatch.setattr(main, 'source_mode', 'file')
    history = SequenceHistory(); history.reset(source)
    players = [{'id': '1', 'team': 'home', 'x': .2, 'y': .3}, {'id': '2', 'team': 'home', 'x': .4, 'y': .5}]
    metrics = {'team_width_m': 10., 'team_length_m': 20.}
    feedback = [{'observation': '검증용 관찰', 'interpretation': '시험', 'suggestion': '시험', 'limitations': '합성 데이터'}]
    assert history.add(source, 10, 10., frame_at(source, 10), players, metrics, feedback, teams_validated=True, calibration_validated=True)
    monkeypatch.setattr(main, 'sequence_history', history)
    client = TestClient(main.app)
    item = client.post('/api/v1/sequences', json={'start_s': .2, 'end_s': 1.8}).json()
    assert item['snapshot_available'] is True and item['snapshot_frame_index'] == 10
    assert item['snapshot_offset_s'] == .8 and item['players'] == players and item['metrics'] == metrics
    response = client.get('/api/v1/sequences/' + item['id'] + '/snapshot.jpg')
    assert response.status_code == 200 and response.headers['content-type'].startswith('image/jpeg')
    assert cv2.imdecode(np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_COLOR) is not None
    gateway = TestClient(plaintext_demo.create_app('127.0.0.1', upstream_transport=httpx.ASGITransport(app=main.app)), client=('127.0.0.1', 1234))
    image = gateway.get('/api/v1/sequences/' + item['id'] + '/snapshot.jpg')
    assert image.status_code == 200 and image.content == response.content
    assert gateway.get('/api/v1/sequences/not-an-id/snapshot.jpg').status_code == 404
    history.reset()
    empty = client.post('/api/v1/sequences', json={'start_s': .2, 'end_s': 1.8}).json()
    assert empty.get('snapshot_available') is not True and empty['players'] == [] and empty['feedback'] == []
    assert client.get('/api/v1/sequences/' + empty['id'] + '/snapshot.jpg').status_code == 404
