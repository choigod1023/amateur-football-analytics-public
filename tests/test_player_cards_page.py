import json

from fastapi.testclient import TestClient

from app.review_public import create_app

HEADERS = {'Origin': 'http://example.test'}


def client(tmp_path):
    return TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')


def test_without_cards_the_list_is_empty(tmp_path):
    data = client(tmp_path).post('/api/v1/cards/list', json={}, headers=HEADERS).json()
    assert data == {'cards': [], 'made': None}


def test_the_cards_are_listed_and_served_and_other_names_are_refused(tmp_path):
    folder = tmp_path / 'cards'
    folder.mkdir()
    (folder / 'card_17.png').write_bytes(b'PNG fake')
    (folder / 'secret.png').write_bytes(b'x')
    (folder / 'summary.json').write_text(json.dumps([{'player': 'a', 'number': 17, 'file': 'card_17.png', 'seconds': 60, 'distance': 100, 'top_kmh': 20, 'sprints': 1}]), encoding='utf-8')
    c = client(tmp_path)
    data = c.post('/api/v1/cards/list', json={}, headers=HEADERS).json()
    assert data['cards'][0]['file'] == 'card_17.png' and data['made'] > 0
    assert c.get('/card-files/card_17.png').status_code == 200 and c.get('/card-files/card_17.png').headers['content-type'] == 'image/png'
    assert c.get('/card-files/secret.png').status_code == 404 and c.get('/card-files/card_99.png').status_code == 404
    assert c.get('/cards').status_code == 200 and c.get('/cards.js').status_code == 200
