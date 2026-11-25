"""/live-hls/<file> passes MediaMTX's HLS output on unchanged and refuses everything else; the receiver config binds HLS to 127.0.0.1."""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import live_video_routes
from app.srt_path_ingest import config_for


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = FastAPI()
    live_video_routes.install(app, tmp_path)
    return TestClient(app, raise_server_exceptions=False)


def fake_get(status=200, body=b'#EXTM3U', headers=None, seen=None):
    def get(url, **kwargs):
        if seen is not None:
            seen.append((url, kwargs))
        return httpx.Response(status, content=body, headers=headers or {})
    return get


def test_playlist_is_passed_on_without_cache(client, monkeypatch):
    seen = []
    monkeypatch.setattr(live_video_routes.httpx, 'get', fake_get(seen=seen))
    r = client.get('/live-hls/index.m3u8')
    assert r.status_code == 200 and r.content == b'#EXTM3U'
    assert r.headers['cache-control'] == 'no-store'
    assert r.headers['content-type'].startswith('application/vnd.apple.mpegurl')
    assert seen[0][0] == 'http://127.0.0.1:18888/match/index.m3u8' and seen[0][1]['timeout'] == 2.0


@pytest.mark.parametrize('name,kind', [('a_init.mp4', 'video/mp4'), ('seg1.m4s', 'video/iso.segment'), ('s-1.ts', 'video/mp2t')])
def test_allowed_pieces(client, monkeypatch, name, kind):
    monkeypatch.setattr(live_video_routes.httpx, 'get', fake_get(body=b'x'))
    r = client.get('/live-hls/' + name)
    assert r.status_code == 200 and r.headers['content-type'] == kind


@pytest.mark.parametrize('path', ['/live-hls/index.html', '/live-hls/a.m3u8.exe', '/live-hls/secret.json', '/live-hls/a b.m3u8', '/live-hls/..m3u8',
                                  '/live-hls/.hidden.m3u8', '/live-hls/../index.m3u8', '/live-hls/..%2Findex.m3u8', '/live-hls/%2e%2e/x.m3u8', '/live-hls/a%5Cb.m3u8'])
def test_other_names_and_escapes_are_404_and_never_reach_the_stream_server(client, monkeypatch, path):
    seen = []
    monkeypatch.setattr(live_video_routes.httpx, 'get', fake_get(seen=seen))
    assert client.get(path).status_code == 404
    assert seen == []


def test_no_stream_server_is_502(client, monkeypatch):
    def down(url, **kwargs):
        raise httpx.ConnectError('refused')
    monkeypatch.setattr(live_video_routes.httpx, 'get', down)
    assert client.get('/live-hls/index.m3u8').status_code == 502


def test_timeout_is_502(client, monkeypatch):
    def slow(url, **kwargs):
        raise httpx.ReadTimeout('slow')
    monkeypatch.setattr(live_video_routes.httpx, 'get', slow)
    assert client.get('/live-hls/index.m3u8').status_code == 502


def test_missing_stream_is_404_and_odd_answer_is_502(client, monkeypatch):
    monkeypatch.setattr(live_video_routes.httpx, 'get', fake_get(404))
    assert client.get('/live-hls/index.m3u8').status_code == 404
    monkeypatch.setattr(live_video_routes.httpx, 'get', fake_get(500))
    assert client.get('/live-hls/index.m3u8').status_code == 502


def test_query_is_passed_on_and_the_cookie_check_redirect_is_followed_inside(client, monkeypatch):
    seen = []
    answers = [httpx.Response(302, headers={'location': '/match/index.m3u8?cookieCheck=1'}), httpx.Response(200, content=b'#EXTM3U')]

    def get(url, **kwargs):
        seen.append(url)
        return answers.pop(0)
    monkeypatch.setattr(live_video_routes.httpx, 'get', get)
    r = client.get('/live-hls/index.m3u8')
    assert r.status_code == 200 and seen == ['http://127.0.0.1:18888/match/index.m3u8', 'http://127.0.0.1:18888/match/index.m3u8?cookieCheck=1']
    monkeypatch.setattr(live_video_routes.httpx, 'get', fake_get(seen=seen))
    assert client.get('/live-hls/video1_stream.m3u8?session=ab-12').status_code == 200
    assert seen[-1][0].endswith('/match/video1_stream.m3u8?session=ab-12')
    assert client.get('/live-hls/index.m3u8?x=a:b').status_code == 404


def test_redirect_elsewhere_is_not_followed(client, monkeypatch):
    monkeypatch.setattr(live_video_routes.httpx, 'get', fake_get(302, b'', {'location': 'http://evil.example/'}))
    assert client.get('/live-hls/index.m3u8').status_code == 502


def test_range_is_forwarded(client, monkeypatch):
    seen = []
    monkeypatch.setattr(live_video_routes.httpx, 'get', fake_get(206, b'ab', {'content-range': 'bytes 0-1/10'}, seen))
    r = client.get('/live-hls/a.mp4', headers={'Range': 'bytes=0-1'})
    assert r.status_code == 206 and r.headers['content-range'] == 'bytes 0-1/10'
    assert seen[0][1]['headers'] == {'Range': 'bytes=0-1'}


OLD_CONFIG_LINES = """logLevel: error
rtsp: true
rtspAddress: 127.0.0.1:18554
rtspTransports: [tcp]
rtmp: false
webrtc: false
moq: false
srt: true
srtAddress: 192.168.0.10:8890
api: false
metrics: false
pprof: false
playback: false
authMethod: internal
authInternalUsers:
  - user: any
    ips: []
    permissions:
      - action: publish
        path: match
  - user: any
    ips: [127.0.0.1/32]
    permissions:
      - action: read
        path: match
paths:
  match:
    srtPublishPassphrase: invalid_config_not_for_direct_use
    overridePublisher: false
    record: true
    recordFormat: fmp4
    recordPartDuration: 1s
    recordSegmentDuration: 10m
    recordDeleteAfter: 0s""".splitlines()


def test_config_binds_hls_to_loopback_and_changes_nothing_else():
    config = config_for('192.168.0.10', '127.0.0.1', 8890, 18554, record=True, allow_any_publisher=True).splitlines()
    assert 'hls: true' in config and 'hlsAddress: 127.0.0.1:18888' in config
    assert 'hlsVariant: fmp4' in config and 'hlsAllowOrigins: []' in config and 'hls: false' not in config
    assert 'hlsSegmentDuration: 1s' in config and 'hlsSegmentCount: 5' in config     # pieces end at the next key frame after 1 s
    assert [line for line in config if not line.startswith('hls')] == OLD_CONFIG_LINES


def test_hls_port_is_checked():
    assert 'hlsAddress: 127.0.0.1:28888' in config_for('127.0.0.1', '127.0.0.1', 28700, 28554, hls_port=28888)
    for bad in (80, 70000, 18554, 18890, '18888', True):
        with pytest.raises(ValueError):
            config_for('127.0.0.1', '127.0.0.1', 18890, 18554, hls_port=bad)


def test_hls_js_file_is_served_from_this_server_and_the_screens_name_no_other_host(tmp_path):
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / 'web'
    app = FastAPI()
    live_video_routes.install(app, web)
    r = TestClient(app).get('/vendor/hls.min.js')
    assert r.status_code == 200 and r.headers['content-type'].startswith('application/javascript')
    import hashlib
    readme = (web / 'vendor' / 'README.md').read_text(encoding='utf-8')
    assert hashlib.sha256(r.content).hexdigest() in readme
    for name in ('live.html', 'bench.html', 'setup.html', 'live-hls.js'):
        assert not re.search(r'https?://', (web / name).read_text(encoding='utf-8')), name


def test_hls_js_is_loaded_only_by_live_hls_js_and_the_csp_allows_the_video_blob():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    script = (root / 'web' / 'live-hls.js').read_text(encoding='utf-8')
    assert "'/vendor/hls.min.js'" in script and 'hls=js' in script and 'canPlayType' in script
    assert "media-src 'self' blob:" in (root / 'app' / 'review_public.py').read_text(encoding='utf-8')
