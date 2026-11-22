from fastapi.testclient import TestClient
from app.plaintext_demo import create_app
import socket
import threading
import time
import httpx
import uvicorn


def test_static_opt_in_and_read_only(tmp_path):
    root = tmp_path / 'site'
    (root / 'assets').mkdir(parents=True)
    (root / 'index.html').write_text('<title>dashboard</title>', encoding='utf-8')
    (root / 'assets' / 'main.js').write_text('export const value=1;', encoding='utf-8')
    (root / '.secret.js').write_text('not public', encoding='utf-8')
    (tmp_path / 'outside.html').write_text('outside', encoding='utf-8')
    client = TestClient(create_app('127.0.0.1', static_dir=root), client=('127.0.0.1', 1111))
    assert client.get('/').status_code == 200
    assert client.get('/').headers['cache-control'] == 'no-store'
    assert 'dashboard' in client.get('/').text
    assert client.get('/assets/main.js').status_code == 200
    assert client.get('/.secret.js').status_code == 404
    assert client.get('/%2e%2e/outside.html').status_code == 404
    assert client.get('/assets/%2e%2e/%2e%2e/outside.html').status_code == 404
    assert client.get('/api/v1/start').status_code == 404
    assert client.post('/api/v1/start').status_code == 404
    assert client.get('/docs').status_code == 404
    assert client.post('/').status_code == 405
    assert TestClient(create_app('127.0.0.1'), client=('127.0.0.1', 1111)).get('/').status_code == 404


def test_existing_static_directory_cannot_bypass_source_restriction(tmp_path):
    (tmp_path / 'index.html').write_text('site', encoding='utf-8')
    client = TestClient(create_app('127.0.0.1', static_dir=tmp_path), client=('127.0.0.2', 1111))
    assert client.get('/').status_code == 403


def test_static_page_is_served_over_real_local_http(tmp_path):
    (tmp_path / 'index.html').write_text('<title>dashboard</title>', encoding='utf-8')
    sock=socket.socket(); sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]; sock.close()
    server=uvicorn.Server(uvicorn.Config(create_app('127.0.0.1', static_dir=tmp_path), host='127.0.0.1', port=port, log_level='error', access_log=False, proxy_headers=False))
    thread=threading.Thread(target=server.run,daemon=True); thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline: time.sleep(.02)
        assert server.started
        with httpx.Client(trust_env=False) as client:
            response=client.get(f'http://127.0.0.1:{port}/')
            assert response.status_code==200 and 'dashboard' in response.text
            assert response.headers['cache-control']=='no-store'
            assert client.post(f'http://127.0.0.1:{port}/api/v1/start').status_code==404
    finally:
        server.should_exit=True; thread.join(timeout=5)
        assert not thread.is_alive()
