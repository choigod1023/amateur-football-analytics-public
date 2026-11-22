import threading
import time
import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient
import app.main as backend
from app.plaintext_demo import create_app


def make_mp4(path):
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),10,(64,48))
    assert writer.isOpened()
    for _ in range(5): writer.write(np.zeros((48,64,3),dtype=np.uint8))
    writer.release()
    return path.read_bytes()


def test_upload_validates_and_switches_modes(tmp_path,monkeypatch):
    payload=make_mp4(tmp_path/'example.mp4')
    monkeypatch.setattr(backend,'UPLOAD_DIR',tmp_path/'uploads')
    monkeypatch.setattr(backend,'worker',None)
    monkeypatch.setattr(backend,'source_mode','live')
    def mock_run(source, config):
        backend.stop_event.wait(4)
        backend.set_state(backend.status,status='idle')
    monkeypatch.setattr(backend,'run',mock_run)
    with TestClient(backend.app) as client:
        assert client.post('/api/v1/upload',content=b'bad',headers={'content-type':'text/plain'}).status_code==415
        assert client.post('/api/v1/upload',content=b'bad',headers={'content-type':'video/mp4'}).status_code==415
        assert client.post('/api/v1/upload',content=b'',headers={'content-type':'video/mp4','content-length':str(backend.UPLOAD_MAX_BYTES+1)}).status_code==413
        assert not list((tmp_path/'uploads').glob('*'))
        result=client.post('/api/v1/upload',content=payload,headers={'content-type':'video/mp4','x-filename':'../../unsafe.mp4'})
        assert result.status_code==200 and result.json()['accepted'] is True
        files=list((tmp_path/'uploads').iterdir())
        assert len(files)==1 and files[0].name.endswith('.mp4') and files[0].read_bytes()==payload
        status=client.get('/api/v1/status').json()
        assert status['input_mode']=='file' and status['source']=='업로드 영상'
        assert client.post('/api/v1/start',json={'source':'rtsp://127.0.0.1:18554/match'}).status_code==409
        assert client.post('/api/v1/live').status_code==200
        assert client.get('/api/v1/status').json()['input_mode']=='live'
        backend.stop_event.set()
        if backend.worker: backend.worker.join(timeout=5)


def test_gateway_only_forwards_designated_upload_and_live_endpoints():
    seen=[]
    async def upstream(request):
        seen.append((request.method,request.url.path,await request.aread()))
        return httpx.Response(200,json={'accepted':True})
    client=TestClient(create_app('127.0.0.1',upstream_transport=httpx.MockTransport(upstream)),client=('127.0.0.1',1234))
    assert client.post('/api/v1/upload',content=b'video',headers={'content-type':'video/mp4'}).status_code==200
    assert seen[-1]==('POST','/api/v1/upload',b'video')
    assert client.post('/api/v1/live').status_code==200
    assert client.post('/api/v1/start',json={'source':'https://invalid'}).status_code==404
    assert client.post('/api/v1/upload',content=b'a',headers={'content-type':'video/mp4','content-length':str(256*1024*1024+1)}).status_code==413
    assert client.get('/api/v1/upload').status_code==405
