import time
import pytest
from fastapi.testclient import TestClient
from app import main
from app.live_bookmarks import LiveBookmarks
from app.read_proxy import create_app as create_proxy
from app.plaintext_demo import create_app as create_public_demo


def test_exact_frame_metadata_staleness_and_capacity():
    book = LiveBookmarks(limit=1, max_age_s=1)
    book.publish(b'first-jpeg', '2026-11-11T00:00:00Z', time.monotonic()-3, 4, {'team_width_m': None}, [])
    with pytest.raises(ValueError, match='no_recent_frame'): book.mark()
    feedback = [{'observation': '표시'}]
    book.publish(b'real-jpeg', '2026-11-11T00:00:01Z', time.monotonic(), 4, {'team_width_m': None}, feedback)
    feedback[0]['observation'] = '변경'
    item = book.mark()
    assert item['kind'] == 'user_marked' and item['people'] == 4
    assert item['feedback'][0]['observation'] == '표시'
    assert book.image(item['id']) == b'real-jpeg'
    with pytest.raises(ValueError, match='limit_reached'): book.mark()
    book.clear_latest()
    assert len(book.list()) == 1  # no implicit removal on stream switch


def test_local_route_gates_other_origins_and_returns_exact_frame(monkeypatch):
    book = LiveBookmarks()
    monkeypatch.setattr(main, 'live_bookmarks', book)
    main.stop_event.clear()
    main.set_state(main.status, status='running', source='rtsp://127.0.0.1:18555/match')
    book.publish(b'real-frame', '2026-11-11T00:00:00Z', time.monotonic(), 3, {'team_width_m': None}, [])
    client = TestClient(main.app)
    assert client.post('/api/v1/live-bookmarks', headers={'Origin': 'https://attacker.example'}).status_code == 403
    response = client.post('/api/v1/live-bookmarks', headers={'Origin': 'http://testserver'})
    assert response.status_code == 200
    identifier = response.json()['id']
    image = client.get(f'/api/v1/live-bookmarks/{identifier}/frame.jpg')
    assert image.content == b'real-frame' and image.headers['cache-control'] == 'no-store'
    assert len(client.get('/api/v1/live-bookmarks').json()['items']) == 1
    main.set_state(main.status, status='idle', source=None)
    assert client.post('/api/v1/live-bookmarks').status_code == 409


def test_bookmark_routes_are_not_added_to_existing_network_gateways():
    with TestClient(create_proxy('a' * 40, allow_manual=True, serve_dashboard=True)) as client:
        headers = {'Authorization': 'Bearer ' + 'a' * 40}
        assert client.get('/api/v1/live-bookmarks', headers=headers).status_code == 404
        assert client.post('/api/v1/live-bookmarks', headers=headers).status_code == 404
    with TestClient(create_public_demo('127.0.0.1', allow_any_viewer=True), client=('127.0.0.1', 5000)) as client:
        assert client.get('/api/v1/live-bookmarks').status_code == 404
        assert client.post('/api/v1/live-bookmarks').status_code == 404
