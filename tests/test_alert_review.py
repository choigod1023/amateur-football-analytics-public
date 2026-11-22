import json

from fastapi.testclient import TestClient

from app.alert_review import AlertReview
from app.review_public import create_app

HEADERS = {'Origin': 'http://example.test'}


def write_session(root, name, alerts, with_image=0):
    folder = root / 'alerts' / name
    folder.mkdir(parents=True)
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(a, ensure_ascii=False) for a in alerts) + '\n', encoding='utf-8')
    if with_image is not None:
        (folder / f'alerts_{with_image:04d}.jpg').write_bytes(b'\xff\xd8jpeg')


ALERTS = [{'time': 12.0, 'kind': 'box_attack', 'title': '박스 침투 공격', 'text': '박스 안에 3명', 'polarity': 'good', 'detail': {'line': '패스길: 열림 2개, 막힘 1개', 'scene': ['a'], 'space': ['b'], 'advice': ['c']}},
          {'time': 40.0, 'kind': 'line_drop', 'title': '수비 라인 하락', 'text': '라인이 내려감', 'polarity': 'poor', 'detail': None}]


def test_listing_marks_counts_and_the_newest_alert_of_a_session_first(tmp_path):
    write_session(tmp_path, 'run-1', ALERTS)
    review = AlertReview(tmp_path)
    assert review.set_label('run-1-0', 'ok', '좋음')['label'] == 'ok'
    review.set_label('run-1-1', 'wrong')
    data = review.listing()
    assert [a['id'] for a in data['alerts']] == ['run-1-1', 'run-1-0']
    first = next(a for a in data['alerts'] if a['id'] == 'run-1-0')
    assert first['label'] == 'ok' and first['note'] == '좋음' and first['image'] == '/alert-files/run-1/alerts_0000.jpg' and first['line'].startswith('패스길')
    stats = {r['kind']: r for r in data['stats']}
    assert stats['box_attack']['useful_share'] == 1.0 and stats['line_drop']['wrong'] == 1 and stats['line_drop']['useful_share'] == 0.0
    review.set_label('run-1-0', '')                                           # clearing a mark
    assert next(a for a in review.listing()['alerts'] if a['id'] == 'run-1-0')['label'] is None


def test_unknown_alerts_and_labels_are_refused_and_images_stay_inside_the_session(tmp_path):
    write_session(tmp_path, 'run-1', ALERTS)
    review = AlertReview(tmp_path)
    for bad in ('run-1-9', 'nope-0', '../x-0', 'run-1'):
        try:
            review.set_label(bad, 'ok')
            raise AssertionError(bad)
        except ValueError:
            pass
    try:
        review.set_label('run-1-0', 'great')
        raise AssertionError('label')
    except ValueError:
        pass
    assert review.image('run-1', 'alerts_0000.jpg') is not None
    assert review.image('run-1', '../alerts.jsonl') is None and review.image('..', 'alerts_0000.jpg') is None and review.image('run-1', 'alerts_0007.jpg') is None


def test_a_damaged_line_keeps_the_numbers_of_the_other_alerts(tmp_path):
    folder = tmp_path / 'alerts' / 'run-2'
    folder.mkdir(parents=True)
    (folder / 'alerts.jsonl').write_text(json.dumps(ALERTS[0]) + '\n{not json\n' + json.dumps(ALERTS[1]) + '\n', encoding='utf-8')
    review = AlertReview(tmp_path)
    assert sorted(a['id'] for a in review.listing()['alerts']) == ['run-2-0', 'run-2-2']
    review.set_label('run-2-2', 'useless')
    try:
        review.set_label('run-2-1', 'ok')
        raise AssertionError('damaged line')
    except ValueError:
        pass


def test_the_pages_and_the_api_work_through_the_server(tmp_path):
    write_session(tmp_path, 'run-1', ALERTS)
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    assert client.get('/alerts').status_code == 200 and client.get('/alerts.js').status_code == 200 and client.get('/alerts.css').status_code == 200
    assert client.post('/api/v1/alerts/label', json={'id': 'run-1-0', 'label': 'ok'}).status_code == 403          # a post needs the origin of the server
    assert client.post('/api/v1/alerts/label', json={'id': 'run-1-0', 'label': 'ok'}, headers=HEADERS).json()['saved']['label'] == 'ok'
    assert client.post('/api/v1/alerts/label', json={'id': 'run-1-0', 'label': 'bad'}, headers=HEADERS).status_code == 409
    data = client.post('/api/v1/alerts/list', headers=HEADERS).json()
    assert len(data['alerts']) == 2 and data['stats'][0]['total'] >= 1
    assert client.get('/alert-files/run-1/alerts_0000.jpg').headers['content-type'] == 'image/jpeg'
    assert client.get('/alert-files/run-1/alerts_0001.jpg').status_code == 404
    assert client.get('/alert-files/run-1/..%2Falerts.jsonl').status_code == 404
