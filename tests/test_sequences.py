import shutil
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main, sequence_store as store
from app.plaintext_demo import create_app


def require_ffmpeg():
    try:
        store.find_ffmpeg()
    except store.SequenceError:
        pytest.skip('FFmpeg not available')


@pytest.fixture
def uploaded(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'UPLOADS', tmp_path / 'uploads')
    monkeypatch.setattr(store, 'SEQUENCES', tmp_path / 'sequences')
    store.UPLOADS.mkdir()
    sample = store.UPLOADS / 'source.mp4'
    writer = cv2.VideoWriter(str(sample), cv2.VideoWriter_fourcc(*'mp4v'), 10, (160, 90))
    assert writer.isOpened()
    for index in range(30):
        frame = np.full((90, 160, 3), (index * 7 % 255, 40, 100), dtype=np.uint8)
        writer.write(frame)
    writer.release()
    monkeypatch.setitem(main.status, 'source', str(sample))
    monkeypatch.setattr(main, 'source_mode', 'file')
    return sample


def test_manual_sequence_real_video_and_range(uploaded):
    require_ffmpeg()
    client = TestClient(main.app)
    result = client.post('/api/v1/sequences', json={'start_s': .2, 'end_s': 1.8})
    assert result.status_code == 200, result.text
    item = result.json()
    assert len(item['id']) == 32 and item['status'] == 'ready'
    assert item['players'] == item['feedback'] == []
    assert all(value is None for value in item['metrics'].values())
    assert client.get('/api/v1/sequences').json()['items'][0]['id'] == item['id']
    video = client.get(f"/api/v1/sequences/{item['id']}/video", headers={'Range': 'bytes=0-99'})
    assert video.status_code == 206 and len(video.content) == 100
    assert video.headers['content-type'].startswith('video/mp4')
    assert 'no-store' in video.headers['cache-control']
    cap = cv2.VideoCapture(str(store.video_path(item['id'])))
    ok, _ = cap.read(); cap.release()
    assert ok
    assert client.get('/api/v1/sequences/' + 'a'*32 + '/video').status_code == 404


def test_reject_unsafe_sources_and_intervals(uploaded, tmp_path, monkeypatch):
    require_ffmpeg()
    client = TestClient(main.app)
    for start, end in [(-1, 1), (2, 1), (0, 21), (0, 4)]:
        assert client.post('/api/v1/sequences', json={'start_s': start, 'end_s': end}).status_code == 400
    outside = tmp_path / 'outside.mp4'; shutil.copyfile(uploaded, outside)
    monkeypatch.setitem(main.status, 'source', str(outside))
    assert client.post('/api/v1/sequences', json={'start_s': 0, 'end_s': 1}).status_code == 409
    monkeypatch.setattr(main, 'source_mode', 'live')
    assert client.post('/api/v1/sequences', json={'start_s': 0, 'end_s': 1}).status_code == 409
    assert main.upload_lock.acquire(blocking=False)
    try:
        assert client.post('/api/v1/sequences', json={'start_s': 0, 'end_s': 1}).status_code == 409
        assert client.post('/api/v1/start', json={'source': str(uploaded)}).status_code == 409
    finally:
        main.upload_lock.release()


def test_gateway_allowlist_and_range(uploaded):
    require_ffmpeg()
    app = create_app('127.0.0.1', upstream_transport=httpx.ASGITransport(app=main.app))
    client = TestClient(app, client=('127.0.0.1', 1234))
    result = client.post('/api/v1/sequences', json={'start_s': 0, 'end_s': 1})
    assert result.status_code == 200, result.text
    ident = result.json()['id']
    assert client.get('/api/v1/sequences').json()['items'][0]['id'] == ident
    video = client.get(f'/api/v1/sequences/{ident}/video', headers={'Range': 'bytes=0-19'})
    assert video.status_code == 206 and len(video.content) == 20
    assert video.headers['content-range'].startswith('bytes 0-19/')
    assert client.get('/api/v1/sequences/not-an-id/video').status_code == 404
    assert client.post('/api/v1/sequences', content=b'x'*1025, headers={'Content-Type':'application/json'}).status_code == 413
    assert client.get('/api/v1/start').status_code == 404
