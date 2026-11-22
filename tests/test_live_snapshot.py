import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from app.live_snapshot import LiveSnapshot, empty_analysis
from app.review_public import create_app


def publish(path, age=0, name='frame-abc123.jpg'):
    value = {'updated_at': (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(),
             'frame_file': name,
             'status': {'status': 'running', 'source': 'C:/private/movie.mp4',
                        'fps': 5.0, 'latency_ms': 40, 'message': 'recorded replay', 'replay': True},
             'analysis': {**empty_analysis(), 'timestamp': datetime.now(timezone.utc).isoformat()}}
    (path / 'snapshot.json').write_text(json.dumps(value), encoding='utf-8')
    (path / 'frame-abc123.jpg').write_bytes(b'\xff\xd8example\xff\xd9')
    return value


def test_fresh_snapshot_and_generation_frame(tmp_path, monkeypatch):
    value = publish(tmp_path)
    monkeypatch.setenv('FOOTBALL_LIVE_SNAPSHOT_DIR', str(tmp_path))
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    status = client.get('/api/v1/status').json()
    assert status['status'] == 'running' and status['replay'] is True
    assert status['source'] == 'recorded_replay'
    assert client.get('/api/v1/analysis').json() == value['analysis']
    frame = client.get('/api/v1/frame.jpg')
    assert frame.status_code == 200 and frame.headers['content-type'] == 'image/jpeg'
    assert frame.headers['x-frame-timestamp'] == value['updated_at']
    assert 0 <= float(frame.headers['x-frame-age-ms']) < 3000


def test_stale_snapshot_has_no_positions_or_frame(tmp_path, monkeypatch):
    publish(tmp_path, age=4)
    monkeypatch.setenv('FOOTBALL_LIVE_SNAPSHOT_DIR', str(tmp_path))
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    assert client.get('/api/v1/status').json()['status'] == 'error'
    assert client.get('/api/v1/analysis').json() == empty_analysis()
    assert client.get('/api/v1/frame.jpg').status_code == 503


def test_malformed_future_and_traversal_are_rejected(tmp_path):
    reader = LiveSnapshot(tmp_path)
    assert reader.read() is None
    (tmp_path / 'snapshot.json').write_text('{partial', encoding='utf-8')
    assert reader.read() is None
    publish(tmp_path, age=-20)
    assert reader.read() is None
    for name in ('../frame-secret.jpg', '/frame-secret.jpg', 'frame-a/../../secret.jpg'):
        publish(tmp_path, name=name)
        assert reader.read() is None
    value = publish(tmp_path)
    value['status']['fps'] = float('nan')
    (tmp_path / 'snapshot.json').write_text(json.dumps(value), encoding='utf-8')
    assert reader.read() is None


def test_stopped_snapshot_does_not_serve_last_frame(tmp_path):
    value = publish(tmp_path)
    value['status']['status'] = 'idle'
    (tmp_path / 'snapshot.json').write_text(json.dumps(value), encoding='utf-8')
    assert LiveSnapshot(tmp_path).frame() is None
