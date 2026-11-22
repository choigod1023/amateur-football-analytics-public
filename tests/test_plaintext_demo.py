import httpx
import socket
import threading
import time
import uvicorn
from fastapi.testclient import TestClient
from app.plaintext_demo import create_app, demo_srt_config


def upstream(request):
    if request.url.path.endswith('frame.jpg'):
        return httpx.Response(200,headers={'content-type':'image/jpeg','x-frame-timestamp':'2026-01-01T00:00:00Z'},content=b'jpeg')
    return httpx.Response(200,headers={'content-type':'application/json'},json={'ok':True})


def test_readonly_and_source_enforcement():
    app=create_app('127.0.0.1',httpx.MockTransport(upstream))
    client=TestClient(app,client=('127.0.0.1',1234))
    assert client.get('/api/v1/status').json()=={'ok':True}
    frame=client.get('/api/v1/frame.jpg')
    assert frame.content==b'jpeg' and frame.headers['cache-control']=='no-store' and 'x-frame-timestamp' in frame.headers
    assert client.post('/api/v1/start').status_code==404
    assert client.post('/api/v1/status').status_code==405
    assert client.get('/docs').status_code==404
    other=TestClient(app,client=('127.0.0.2',1234))
    assert other.get('/api/v1/status',headers={'x-forwarded-for':'127.0.0.1'}).status_code==403


def test_srt_demo_is_source_restricted_without_passphrase():
    config=demo_srt_config('127.0.0.1','127.0.0.1')
    assert 'ips: [127.0.0.1/32]' in config
    assert 'srtPublishPassphrase:' not in config
    assert 'api: false' in config and 'overridePublisher: false' in config


def test_cellular_option_opens_only_srt_publishing():
    config=demo_srt_config('127.0.0.1','127.0.0.1', allow_cellular=True)
    assert config.count('ips: []') == 1
    assert config.count('ips: [127.0.0.1/32]') == 1
    assert 'rtspAddress: 127.0.0.1:18554' in config


def test_explicit_public_viewer_option_remains_read_only():
    app=create_app('127.0.0.1',httpx.MockTransport(upstream),allow_any_viewer=True)
    client=TestClient(app,client=('127.0.0.2',1234))
    assert client.get('/api/v1/status').status_code==200
    assert client.get('/api/v1/frame.jpg').status_code==200
    assert client.post('/api/v1/start').status_code==404
    assert client.get('/docs').status_code==404


def test_actual_tcp_gateway():
    sock=socket.socket(); sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]; sock.close()
    app=create_app('127.0.0.1',httpx.MockTransport(upstream))
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False,proxy_headers=False))
    thread=threading.Thread(target=server.run,daemon=True); thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline: time.sleep(.02)
        assert server.started
        base=f'http://127.0.0.1:{port}'
        with httpx.Client(trust_env=False) as client:
            assert client.get(base+'/api/v1/status').status_code==200
            assert client.get(base+'/api/v1/frame.jpg').status_code==200
            assert client.post(base+'/api/v1/start').status_code==404
        with httpx.Client(transport=httpx.HTTPTransport(local_address='127.0.0.2'),trust_env=False) as client:
            assert client.get(base+'/api/v1/status',headers={'x-forwarded-for':'127.0.0.1'}).status_code==403
    finally:
        server.should_exit=True; thread.join(timeout=5)
        assert not thread.is_alive()
