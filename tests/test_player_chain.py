import json

from fastapi.testclient import TestClient

from app.player_identity import PlayerIdentity
from app.review_public import create_app

HEADERS = {'Origin': 'http://example.test'}


def track(ident, team, first, last, a, b, slot='LCB', rows=100):
    return {'id': ident, 'team': team, 'first': first, 'last': last, 'rows': rows, 'u': (a[0] + b[0]) / 2, 'y': (a[1] + b[1]) / 2, 'height': 30, 'slot': slot, 'formation': None,
            'pictures': [], 'first_pos': list(a), 'last_pos': list(b)}


def prepare(tmp_path):
    folder = tmp_path / 'players' / 'h1'
    folder.mkdir(parents=True)
    tracks = [track('1', 'B', 0.0, 40.0, (-30, 0), (-25, 5)),                       # the player starts here
              track('2', 'B', 42.0, 80.0, (-24, 6), (-20, 8)),                      # follows 1 closely: offered first
              track('3', 'B', 45.0, 90.0, (10, 20), (15, 20)),                      # far away from where 1 ended: not offered
              track('4', 'B', 82.0, 100.0, (-19, 9), (-18, 10), slot='ST'),         # follows 2 closely but is a forward track: offered, ranked low and marked as not fitting
              track('5', 'B', 10.0, 30.0, (-29, 1), (-26, 4)),                      # overlaps 1 in time: never offered
              track('6', 'A', 41.0, 60.0, (-24, 5), (-22, 6)),                      # the other team: never offered
              track('7', 'B', 200.0, 240.0, (-20, 8), (-15, 3))]                    # a long gap: not offered
    (folder / 'index.json').write_text(json.dumps({'name': '전반', 'tracks': tracks, 'candidates': []}), encoding='utf-8')


def test_a_player_without_tracks_is_started_from_the_tracks_of_his_line_longest_first(tmp_path):
    prepare(tmp_path)
    ids = PlayerIdentity(tmp_path)
    ids.set_player('', 'B', '수비수', 5, 'DF')
    result = ids.chain('h1', 'p1')
    assert result['mine'] == [] and [o['id'] for o in result['offers']][:2] == ['1', '2'] or result['offers'][0]['line_match'] is True
    assert all(o['team'] == 'B' for o in result['offers']) and result['offers'][-1]['line_match'] is False                       # the forward track comes last


def test_the_next_tracks_follow_in_time_and_place_and_the_answers_change_the_offers(tmp_path):
    prepare(tmp_path)
    ids = PlayerIdentity(tmp_path)
    ids.set_player('', 'B', '수비수', 5, 'DF')
    ids.assign('h1', '1', 'p1')
    offers = ids.chain('h1', 'p1')['offers']
    assert [o['id'] for o in offers] == ['2', '4']                                  # 3 is far, 5 overlaps, 6 is the other team, 7 comes after too long a gap; 4 is possible but a forward track
    assert offers[0]['direction'] == 'after' and offers[0]['gap'] == 2.0 and offers[0]['anchor'] == '1' and offers[0]['line_match'] is True and offers[1]['line_match'] is False
    ids.assign('h1', '2', 'p1')
    nxt = ids.chain('h1', 'p1')
    assert [o['id'] for o in nxt['offers']] == ['4'] and nxt['offers'][0]['anchor'] == '2' and nxt['seconds'] == 78.0       # now 4 follows 2 at a gap of 2 s
    ids.set_reject('h1', 'p1', '4')
    assert ids.chain('h1', 'p1')['offers'] == []
    ids.set_reject('h1', 'p1', '4', False)
    assert [o['id'] for o in ids.chain('h1', 'p1')['offers']] == ['4']


def test_tracks_of_another_player_or_in_conflict_are_not_offered_and_bad_calls_are_refused(tmp_path):
    prepare(tmp_path)
    ids = PlayerIdentity(tmp_path)
    ids.set_player('', 'B', '수비수', 5, 'DF')
    ids.set_player('', 'B', '다른 선수', 6, 'DF')
    ids.assign('h1', '1', 'p1')
    ids.assign('h1', '2', 'p2')
    assert [o['id'] for o in ids.chain('h1', 'p1')['offers']] == ['4']             # 2 belongs to another player now; 4 is still possible
    for call in (lambda: ids.chain('h1', 'p9'), lambda: ids.set_reject('h1', 'p1', '99'), lambda: ids.set_reject('h1', 'p9', '1')):
        try:
            call()
            raise AssertionError('accepted')
        except ValueError:
            pass
    assert ids.chain('zz', 'p1') is None


def test_the_chain_is_served_through_the_api(tmp_path):
    prepare(tmp_path)
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    client.post('/api/v1/players/roster/set', json={'team': 'B', 'name': '수비수', 'number': 5, 'position': 'DF'}, headers=HEADERS)
    client.post('/api/v1/players/assign', json={'half': 'h1', 'track': '1', 'player': 'p1'}, headers=HEADERS)
    data = client.post('/api/v1/players/chain', json={'half': 'h1', 'player': 'p1'}, headers=HEADERS).json()
    assert [o['id'] for o in data['offers']] == ['2', '4'] and data['mine'][0]['id'] == '1' and data['line'] == 'DF'
    assert client.post('/api/v1/players/reject', json={'half': 'h1', 'player': 'p1', 'track': '2'}, headers=HEADERS).json()['rejected'] is True
    assert [o['id'] for o in client.post('/api/v1/players/chain', json={'half': 'h1', 'player': 'p1'}, headers=HEADERS).json()['offers']] == ['4']
    assert client.post('/api/v1/players/chain', json={'half': 'zz', 'player': 'p1'}, headers=HEADERS).status_code == 404
    assert client.post('/api/v1/players/chain', json={'half': 'h1', 'player': 'p9'}, headers=HEADERS).status_code == 409


def test_a_suggested_number_moves_a_track_forward_or_back_and_a_skip_goes_last(tmp_path):
    prepare(tmp_path)
    folder = tmp_path / 'players' / 'suggestions'
    folder.mkdir()
    ids = PlayerIdentity(tmp_path)
    ids.set_player('', 'B', 'defender', 5, 'DF')
    # a player without tracks is started from the tracks of his line: a track with his number first, one with another number after those with none, a skip last
    (folder / 'h1.json').write_text(json.dumps({'2': {'number': 5, 'level': 'clear', 'text': 'read'}, '1': {'number': 9, 'level': 'clear', 'text': 'read'}, '4': {'number': None, 'level': 'skip', 'text': 'referee'}}), encoding='utf-8')
    start = [o['id'] for o in ids.chain('h1', 'p1')['offers']]
    assert start[0] == '2' and start.index('1') > start.index('3') and start[-1] == '4'
    # with a track of his own, a skip falls behind the other offer
    (folder / 'h1.json').write_text(json.dumps({'2': {'number': None, 'level': 'skip', 'text': 'referee'}}), encoding='utf-8')
    ids.assign('h1', '1', 'p1')
    offers = ids.chain('h1', 'p1')['offers']
    assert [o['id'] for o in offers] == ['4', '2'] and offers[1]['suggestion']['level'] == 'skip'
