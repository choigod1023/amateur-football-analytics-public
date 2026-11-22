import json

from fastapi.testclient import TestClient

from app.read_proxy import create_app


TOKEN = 'a' * 40
AUTH = {'Authorization': 'Bearer ' + TOKEN}
ORIGIN = 'https://dashboard.example'


def test_manual_routes_are_disabled_by_default():
    with TestClient(create_app(TOKEN)) as client:
        assert client.get('/').status_code == 404
        assert client.get('/api/v1/manual-snapshot', headers=AUTH).status_code == 404
        assert client.post('/api/v1/manual-track', headers=AUTH, json={}).status_code == 404
        assert client.get('/api/v1/proxy-capabilities').status_code == 401
        assert client.get('/api/v1/proxy-capabilities', headers=AUTH).json() == {'manual_enabled': False, 'controls_enabled': False}


def test_optional_dashboard_is_only_static_and_does_not_expose_extra_paths():
    with TestClient(create_app(TOKEN, ORIGIN, allow_manual=True, serve_dashboard=True)) as client:
        page = client.get('/')
        assert page.status_code == 200 and page.headers['cache-control'] == 'no-store'
        assert client.get('/live-video.js').status_code == 200
        assert "frame-ancestors 'none'" in page.headers['content-security-policy']
        assert "img-src 'self' data: blob:" in page.headers['content-security-policy']
        assert client.get('/api/v1/manual-snapshot').status_code == 401
        assert client.get('/api/v1/proxy-capabilities', headers=AUTH).json() == {'manual_enabled': True, 'controls_enabled': False}
        assert client.get('/config.json', headers=AUTH).status_code == 404
        assert client.post('/api/v1/start', headers=AUTH, json={}).status_code == 404


def test_manual_proxy_requires_authorization_and_exact_origin(monkeypatch):
    observed = []

    class Result:
        status_code = 409
        content = b'{"detail":"expired"}'
        def json(self): return json.loads(self.content)

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            observed.append((url, kwargs))
            return Result()
        async def get(self, url):
            observed.append((url, {}))
            return Result()

    monkeypatch.setattr('app.read_proxy.httpx.AsyncClient', Client)
    app = create_app(TOKEN, ORIGIN, allow_manual=True)
    with TestClient(app) as client:
        path = '/api/v1/manual-track'
        assert client.post(path, json={}).status_code == 401
        assert client.post(path, headers={**AUTH, 'Origin': 'https://evil.example'}, json={}).status_code == 403
        assert client.post(path, headers=AUTH, content=b'{}').status_code == 415
        assert client.post(path, headers={**AUTH, 'Content-Type': 'application/json'}, content=b'x' * 4097).status_code == 413
        pre = client.options(path, headers={'Origin': ORIGIN, 'Access-Control-Request-Method': 'POST',
                                            'Access-Control-Request-Headers': 'authorization,content-type'})
        assert pre.status_code == 204 and pre.headers['access-control-allow-origin'] == ORIGIN
        assert client.options(path, headers={'Origin': ORIGIN, 'Access-Control-Request-Method': 'GET'}).status_code == 403
        response = client.post(path, headers={**AUTH, 'Origin': ORIGIN}, json={'id': '1'})
        assert response.status_code == 409 and response.json() == {'detail': 'expired'}
        assert response.headers['cache-control'] == 'no-store'
        assert len(observed) == 1 and observed[0][0] == 'http://127.0.0.1:8000/api/v1/manual-track'
        assert observed[0][1]['headers'] == {'Content-Type': 'application/json'}
        snapshot = client.get('/api/v1/manual-snapshot', headers=AUTH)
        assert snapshot.status_code == 409 and snapshot.json() == {'detail': 'expired'}
        assert snapshot.headers['cache-control'] == 'no-store'
