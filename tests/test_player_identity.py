import json

from fastapi.testclient import TestClient

from app.player_identity import PlayerIdentity
from app.review_public import create_app

HEADERS = {'Origin': 'http://example.test'}


def prepare(tmp_path):
    folder = tmp_path / 'players' / 'h1'
    folder.mkdir(parents=True)
    tracks = [{'id': '10', 'team': 'B', 'first': 5.0, 'last': 30.0, 'rows': 120, 'u': 10.0, 'y': 3.0, 'height': 30, 'slot': 'LCB', 'formation': '4-4-2', 'pictures': ['10_0.jpg']},
              {'id': '11', 'team': 'B', 'first': 31.0, 'last': 60.0, 'rows': 140, 'u': 11.0, 'y': 4.0, 'height': 31, 'slot': 'LCB', 'formation': '4-4-2', 'pictures': []},
              {'id': '12', 'team': 'A', 'first': 5.0, 'last': 60.0, 'rows': 300, 'u': -5.0, 'y': 0.0, 'height': 29, 'slot': 'ST', 'formation': None, 'pictures': []}]
    (folder / 'index.json').write_text(json.dumps({'name': '전반', 'tracks': tracks, 'candidates': [{'a': '10', 'b': '11', 'gap': 1.0, 'distance': 1.5}]}), encoding='utf-8')
    (folder / '10_0.jpg').write_bytes(b'\xff\xd8jpeg')
    (folder / 'pair_10_11.mp4').write_bytes(b'mp4data')


def test_roster_rules_numbers_are_unique_per_team_and_positions_must_be_known(tmp_path):
    ids = PlayerIdentity(tmp_path)
    a = ids.set_player('', 'B', '민수', 7, 'LB')
    assert a['id'] == 'p1' and ids.set_player('', 'A', '준', 7, '')['id'] == 'p2'              # the same number in the other team is fine
    for bad in (('B', '둘째', 7, ''), ('C', 'x', 1, ''), ('B', 'x', 100, ''), ('B', 'x', 5, 'XX'), ('B', '', None, ''), ('B', 'x', 'a', '')):
        try:
            ids.set_player('', *bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    assert ids.set_player('p1', 'B', '민수2', 7, 'RB')['name'] == '민수2'                       # a change keeps the id and may keep its number
    assert {p['id'] for p in ids.roster()} == {'p1', 'p2'}


def test_answers_links_and_groups(tmp_path):
    prepare(tmp_path)
    ids = PlayerIdentity(tmp_path)
    ids.set_player('', 'B', '민수', 7, 'LCB')
    ids.set_player('', 'A', '준', 9, 'ST')
    assert ids.halves() == ['h1']
    state = ids.state('h1')
    assert state['total'] == 3 and state['done'] == 0 and state['candidates_left'] == 1
    assert ids.assign('h1', '10', 'p1') == 'p1'
    try:
        ids.assign('h1', '12', 'p1')                                                         # a track of team A cannot be a player of team B
        raise AssertionError('other team')
    except ValueError:
        pass
    ids.link('h1', '10', '11', 'same')
    state = ids.state('h1')
    by_id = {t['id']: t for t in state['tracks']}
    assert by_id['11']['player'] is None and by_id['11']['player_by_link'] == 'p1' and by_id['11']['group_size'] == 2 and state['done'] == 2 and state['candidates_left'] == 0
    ids.set_player('', 'B', '지훈', 8, '')
    ids.assign('h1', '11', 'p3')                                                             # two different answers in one group: a conflict, nothing guessed
    assert all(t['conflict'] for t in ids.state('h1')['tracks'] if t['id'] in ('10', '11'))
    ids.link('h1', '10', '11', 'different')                                                  # a new answer replaces the old one
    assert not any(t['conflict'] for t in ids.state('h1')['tracks'])
    assert ids.delete_player('p1') and ids.state('h1')['tracks'][0]['player'] is None        # deleting a player clears the answers that named him


def test_unknown_tracks_and_bad_names_are_refused_and_the_server_serves_the_page(tmp_path):
    prepare(tmp_path)
    ids = PlayerIdentity(tmp_path)
    for call in (lambda: ids.assign('h1', '99', ''), lambda: ids.assign('../x', '10', ''), lambda: ids.link('h1', '10', '10', 'same'), lambda: ids.link('h1', '10', '11', 'maybe')):
        try:
            call()
            raise AssertionError('accepted')
        except ValueError:
            pass
    assert ids.image('h1', '10_0.jpg') is not None and ids.image('h1', '../index.json') is None and ids.image('..', '10_0.jpg') is None
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    assert client.get('/players').status_code == 200 and client.get('/players.js').status_code == 200
    made = client.post('/api/v1/players/roster/set', json={'team': 'B', 'name': '민수', 'number': 7, 'position': 'LB'}, headers=HEADERS)
    assert made.json()['saved']['id'] == 'p1'
    assert client.post('/api/v1/players/assign', json={'half': 'h1', 'track': '10', 'player': 'p1'}, headers=HEADERS).json()['player'] == 'p1'
    state = client.post('/api/v1/players/state', json={'half': 'h1'}, headers=HEADERS).json()
    assert state['halves'] == ['h1'] and state['state']['done'] == 1 and state['position_text']['LB'] == '왼쪽 풀백'
    assert client.post('/api/v1/players/assign', json={'half': 'h1', 'track': '10', 'player': 'p9'}, headers=HEADERS).status_code == 409
    assert client.get('/player-files/h1/10_0.jpg').headers['content-type'] == 'image/jpeg' and client.get('/player-files/h1/11_0.jpg').status_code == 404
    assert client.get('/player-files/h1/pair_10_11.mp4').headers['content-type'] == 'video/mp4' and client.get('/player-files/h1/pair_10_11.exe').status_code == 404
