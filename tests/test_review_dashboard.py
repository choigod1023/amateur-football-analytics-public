import re

from fastapi.testclient import TestClient
from app.review_public import create_app


def test_root_is_the_page_list_and_the_old_dashboard_opens_with_all_assets(tmp_path):
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    first = client.get('/', follow_redirects=False)
    assert first.status_code == 200 and 'location' not in first.headers
    assert first.text == client.get('/start').text
    assert 'href="/alerts"' in first.text and 'href="/train"' in first.text
    page = client.get('/dashboard', follow_redirects=False)
    assert page.status_code == 200
    assert 'location' not in page.headers
    assert 'id="video-player"' in page.text
    assert 'id="feedback"' in page.text
    for path in re.findall(r'(?:src|href)="([^"?#]+\.(?:js|css))"', page.text):
        response = client.get('/' + path)
        assert response.status_code == 200, path
    train = client.get('/train', follow_redirects=False)
    assert train.status_code == 200
    assert train.text != page.text
    status = client.get('/api/v1/status').json()
    assert status['status'] == 'error'
    assert status['source'] is None
    analysis = client.get('/api/v1/analysis').json()
    assert analysis['players'] == [] and analysis['feedback'] == []
    assert analysis['timestamp'] is None and analysis['demo'] is False
