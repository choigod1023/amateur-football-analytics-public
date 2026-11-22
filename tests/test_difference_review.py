import json

import pytest
from fastapi.testclient import TestClient
from app.difference_review import DifferenceReview
from app.review_public import create_app


def fixture(root):
    folder = root / 'differences'
    folder.mkdir()
    rows = [{'id': 'd0001', 'kind': 'tracking', 'title': '<unsafe>', 'reason': 'ambiguous',
             'video': 'd0001.mp4', 'images': ['d0001-a.jpg'], 'before': 'separate', 'after': 'proposal'},
            {'id': 'd0002', 'kind': 'coaching', 'before': 'old', 'after': 'new', 'images': []}]
    (folder / 'queue.json').write_text(json.dumps({'items': rows}), encoding='utf-8')
    (folder / 'd0001.mp4').write_bytes(b'clip')
    (folder / 'd0001-a.jpg').write_bytes(b'image')
    (folder / 'd0099.jpg').write_bytes(b'not listed')
    return folder


def test_stable_queue_preserves_answers_and_never_expires(tmp_path):
    folder = fixture(tmp_path)
    review = DifferenceReview(tmp_path)
    original = (folder / 'queue.json').read_bytes()
    assert review.listing()['remaining'] == 2
    saved = review.answer('d0001', 'same', 'confirmed')
    assert saved['source'] == 'human'
    assert review.answer('d0001', 'same', 'confirmed') == saved
    assert review.listing()['remaining'] == 1
    assert [r['id'] for r in review.listing()['items']] == ['d0002']
    assert len(review.listing(True)['items']) == 2
    before = (folder / 'answers/d0001.json').read_bytes()
    with pytest.raises(ValueError):
        review.answer('d0001', 'different')
    assert (folder / 'answers/d0001.json').read_bytes() == before
    assert (folder / 'queue.json').read_bytes() == original


def test_training_reappearance_route_and_filtered_api(tmp_path):
    folder=fixture(tmp_path)
    data=json.loads((folder/'queue.json').read_text())
    data['items'][0]['review_scope']='occlusion-reappearance'
    (folder/'queue.json').write_text(json.dumps(data))
    with TestClient(create_app(tmp_path, origin='http://testserver')) as client:
        assert client.get('/train/reappearance').status_code==200
        assert '/train/reappearance' in client.get('/train').text
        result=client.get('/api/v1/differences?scope=occlusion-reappearance').json()
        assert result['total']==1 and result['items'][0]['id']=='d0001'
        assert client.get('/api/v1/reappearance/decisions?source_sha256=bad').status_code==400


def test_new_scene_cannot_reuse_an_old_answer(tmp_path):
    folder = fixture(tmp_path)
    review = DifferenceReview(tmp_path)
    review.answer('d0001', 'same')
    queue = json.loads((folder / 'queue.json').read_text())
    queue['items'][0]['before'] = 'changed evidence'
    (folder / 'queue.json').write_text(json.dumps(queue))
    item = review.listing()['items'][0]
    assert not item['answer_is_current']
    assert item['answer']['verdict'] == 'same'
    with pytest.raises(ValueError):
        review.answer('d0001', 'different')


def test_verdict_and_media_validation(tmp_path):
    fixture(tmp_path)
    review = DifferenceReview(tmp_path)
    assert review.media('d0001.mp4') is not None
    for name in ('../queue.json', 'queue.json', 'd0099.jpg', 'd0001-a.jpg/../queue.json'):
        assert review.media(name) is None
    for ident, verdict in [('d0001', 'after'), ('d0002', 'same'), ('../x', 'same'), ('d0099', 'same')]:
        with pytest.raises(ValueError):
            review.answer(ident, verdict)


def test_page_api_same_origin_and_range_media(tmp_path):
    fixture(tmp_path)
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    for path in ('/review-differences', '/differences.js', '/differences.css'):
        assert client.get(path).status_code == 200
    assert client.get('/api/v1/differences').json()['remaining'] == 2
    assert client.post('/api/v1/differences', json={'id': 'd0001', 'verdict': 'same'}).status_code == 403
    assert client.post('/api/v1/differences', json={'id': 'd0002', 'verdict': 'after'}, headers={'Origin': 'http://example.test'}).status_code == 200
    assert client.get('/difference-files/d0001.mp4', headers={'Range': 'bytes=0-1'}).status_code == 206
    assert client.get('/difference-files/d0099.jpg').status_code == 404
