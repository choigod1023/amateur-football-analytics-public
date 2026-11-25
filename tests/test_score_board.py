import json
import time

import pytest
from fastapi.testclient import TestClient

from app.review_public import create_app
from app.score_board import ScoreBoard, analysis_position, compute, confirmed_goals, read_events

ORIGIN = 'http://127.0.0.1:8443'
H = {'Origin': ORIGIN}


class Clock:
    def __init__(self, t=1764061000.0):
        self.t = t

    def __call__(self):
        self.t += 10.0                 # every call is far from the last, so the double-tap guard does not fire unless a test wants it
        return self.t


def make_session(tmp_path, name='match-1', positions=True):
    folder = tmp_path / 'alerts' / name
    folder.mkdir(parents=True)
    rows = [{'time': 5.0, 'kind': 'heartbeat', 'type': 'heartbeat', 'polarity': 'status', 'wall': 1764060990.0}, {'time': 6.5, 'kind': 'box_attack', 'polarity': 'poor', 'title': 'x', 'text': 'y'}]
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
    if positions:
        lines = [{'type': 'header', 'direction': 1}, {'type': 'second', 'time': 4.0, 'team': [], 'other': []}, {'type': 'second', 'time': 7.0, 'team': [], 'other': []}]
        (folder / 'positions.jsonl').write_text('\n'.join(json.dumps(r) for r in lines) + '\n', encoding='utf-8')
    return folder


def test_score_counts_goals_and_one_undo(tmp_path):
    make_session(tmp_path)
    board = ScoreBoard(tmp_path, Clock())
    board.add('match-1', 'goal', 'ours')
    board.add('match-1', 'goal', 'ours')
    board.add('match-1', 'goal', 'opp')
    state = board.add('match-1', 'undo')
    assert (state['ours'], state['opp']) == (2, 0)
    with pytest.raises(ValueError):
        board.add('match-1', 'undo')                      # a second press may not erase a second goal
    assert board.state('match-1')['ours'] == 2 and not board.state('match-1')['can_undo']
    board.add('match-1', 'goal', 'opp')
    assert board.state('match-1')['can_undo'] and board.state('match-1')['last'] == 'opp'


def test_undone_goal_stays_in_the_file_and_is_listed_as_cancelled(tmp_path):
    folder = make_session(tmp_path)
    board = ScoreBoard(tmp_path, Clock())
    board.add('match-1', 'goal', 'ours')
    board.add('match-1', 'goal', 'opp')
    board.add('match-1', 'undo')
    path = folder / 'score.jsonl'
    assert len(read_events(path)) == 3
    assert [g['team'] for g in confirmed_goals(path)] == ['ours']
    both = confirmed_goals(path, include_cancelled=True)
    assert [(g['team'], g['cancelled']) for g in both] == [('ours', False), ('opp', True)]


def test_events_carry_server_time_source_and_analysis_position(tmp_path):
    folder = make_session(tmp_path)
    board = ScoreBoard(tmp_path, Clock())
    board.add('match-1', 'goal', 'ours')
    event = read_events(folder / 'score.jsonl')[0]
    assert event['utc'].endswith('Z') and len(event['utc']) == 24 and event['source'] == 'manual'
    assert event['analysis'] == {'positions_time': 7.0, 'alerts_time': 6.5, 'alerts_wall': 1764060990.0}
    bare = make_session(tmp_path, 'match-2', positions=False)
    (bare / 'alerts.jsonl').write_text('', encoding='utf-8')
    assert analysis_position(bare) is None
    board.add('match-2', 'goal', 'opp')
    assert read_events(bare / 'score.jsonl')[0]['analysis'] is None


def test_candidate_confirm_keeps_candidate_id_and_time_and_dismiss_closes(tmp_path):
    folder = make_session(tmp_path)
    board = ScoreBoard(tmp_path, Clock())
    board.add('match-1', 'candidate', 'opp', 'auto')
    board.add('match-1', 'candidate', 'unknown', 'auto')
    state = board.state('match-1')
    assert [c['id'] for c in state['pending']] == [1, 0] and state['ours'] == 0 and state['opp'] == 0
    state = board.add('match-1', 'goal', 'opp', 'manual', ref=0)
    assert state['opp'] == 1 and [c['id'] for c in state['pending']] == [1]
    with pytest.raises(ValueError):
        board.add('match-1', 'goal', 'opp', 'manual', ref=0)         # a candidate confirms once
    state = board.add('match-1', 'dismiss', None, 'manual', ref=1)
    assert state['pending'] == [] and state['opp'] == 1
    with pytest.raises(ValueError):
        board.add('match-1', 'dismiss', None, 'manual', ref=1)
    goal = confirmed_goals(folder / 'score.jsonl')[0]
    events = read_events(folder / 'score.jsonl')
    assert goal['candidate_id'] == 0 and goal['candidate_utc'] == events[0]['utc'] and goal['candidate_t'] == events[0]['t'] and goal['source'] == 'manual'
    assert events[0]['source'] == 'auto'                                  # the guess is never mixed up with a human press


def test_bad_values_unknown_ref_and_unknown_team_goal_are_refused(tmp_path):
    make_session(tmp_path)
    board = ScoreBoard(tmp_path, Clock())
    for args in [('goal', None), ('goal', 'unknown'), ('candidate', 'nobody')]:
        with pytest.raises(ValueError):
            board.add('match-1', *args)
    with pytest.raises(ValueError):
        board.add('match-1', 'goal', 'ours', 'manual', ref=7)
    with pytest.raises(FileNotFoundError):
        board.add('nothing-here', 'goal', 'ours')
    assert board.state('match-1')['ours'] == 0


def test_double_tap_counts_once(tmp_path):
    make_session(tmp_path)
    board = ScoreBoard(tmp_path, lambda: 1764061000.0)
    board.add('match-1', 'goal', 'ours')
    assert board.add('match-1', 'goal', 'ours')['duplicate'] is True
    assert board.state('match-1')['ours'] == 1
    assert board.add('match-1', 'goal', 'opp')['opp'] == 1             # the other team is a different press


def test_empty_missing_and_damaged_files(tmp_path):
    folder = make_session(tmp_path)
    board = ScoreBoard(tmp_path, Clock())
    assert board.state('match-1')['ours'] == 0 and board.state('match-1')['pending'] == []
    (folder / 'score.jsonl').write_text('', encoding='utf-8')
    assert board.state('match-1')['opp'] == 0
    (folder / 'score.jsonl').write_text('{"id": 0, "kind": "goal", "team": "ours"}\nnot json\n{"id": 1, "kind": "goal", "team": "mars"}\n{"id": 2, "kind": "goal", "team": "opp"', encoding='utf-8')
    assert (board.state('match-1')['ours'], board.state('match-1')['opp']) == (1, 0)      # the cut last line is ignored
    board.add('match-1', 'goal', 'opp')                                                  # and a new line starts on its own line
    assert board.state('match-1')['opp'] == 1
    assert compute([])['can_undo'] is False
    assert ScoreBoard(tmp_path / 'none').state()['session'] is None


def test_live_session_skips_label_sessions_and_person_check(tmp_path):
    make_session(tmp_path, 'older')
    label = tmp_path / 'alerts' / 'label-1'
    label.mkdir()
    (label / 'alerts.jsonl').write_text('{"kind": "team_ours"}\n', encoding='utf-8')
    check = tmp_path / 'alerts' / 'checks'
    check.mkdir()
    (check / 'alerts.jsonl').write_text('{"kind": "person_check"}\n', encoding='utf-8')
    assert ScoreBoard(tmp_path).live_session() == 'older'


@pytest.fixture()
def client(tmp_path):
    make_session(tmp_path)
    return TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN), tmp_path


def post(c, **body):
    return c.post('/api/v1/score', json={'session': 'match-1', 'source': 'manual', **body}, headers=H)


def test_http_score_flow(client):
    c, tmp_path = client
    first = c.get('/api/v1/score').json()
    assert first['session'] == 'match-1' and (first['ours'], first['opp']) == (0, 0)       # no score file: 0 : 0, no error
    assert post(c, kind='goal', team='ours').status_code == 200
    time.sleep(2.1)                                                                         # past the double-tap window
    assert post(c, kind='goal', team='ours').status_code == 200
    assert post(c, kind='goal', team='opp').status_code == 200
    state = post(c, kind='undo').json()
    again = c.get('/api/v1/score').json()
    assert (state['ours'], state['opp']) == (2, 0) == (again['ours'], again['opp'])
    cand = post(c, kind='candidate', team='ours', source='auto').json()
    assert cand['pending'][0]['team'] == 'ours' and cand['ours'] == 2
    ref = cand['pending'][0]['id']
    state = post(c, kind='goal', team='ours', ref=ref).json()
    assert state['ours'] == 3 and state['pending'] == []
    assert post(c, kind='goal', team='ours', ref=ref).status_code == 409


def test_http_rejects_bad_session_values_and_foreign_origin(client):
    c, tmp_path = client
    assert c.get('/api/v1/score', params={'session': '../x'}).status_code == 400
    assert c.get('/api/v1/score', params={'session': 'a b'}).status_code == 400
    assert c.post('/api/v1/score', json={'session': '../x', 'kind': 'undo'}, headers=H).status_code == 400
    assert post(c, kind='goal', team='mars').status_code == 422
    assert post(c, kind='win').status_code == 422
    assert post(c, kind='goal', team='ours', extra=1).status_code == 422
    assert post(c, kind='goal', team='ours', ref=-1).status_code == 422
    assert post(c, kind='goal').status_code == 409
    assert c.post('/api/v1/score', json={'session': 'ghost', 'kind': 'goal', 'team': 'ours'}, headers=H).status_code == 404
    assert not (tmp_path / 'alerts' / 'ghost').exists()
    assert c.post('/api/v1/score', json={'session': 'match-1', 'kind': 'goal', 'team': 'ours'}, headers={'Origin': 'http://evil.example'}).status_code == 403
    assert not (tmp_path / 'alerts' / 'match-1' / 'score.jsonl').exists()


def test_page_has_the_score_board_and_the_old_routes_still_answer(client):
    c, tmp_path = client
    html = c.get('/bench').text
    for needle in ['id="score"', 'id="score-line"', '우리 골', '상대 골', 'id="score-btn-undo"', '/score.js']:
        assert needle in html
    assert 'goal_candidate' not in html and 'score:' not in html
    assert c.get('/score.js').status_code == 200
    assert c.get('/api/v1/bench').status_code == 200 and c.get('/api/v1/bench/minimap').status_code == 200
    assert c.get('/bench.js').status_code == 200 and c.get('/bench-extra.js').status_code == 200


def test_no_session_at_all_gives_zero_zero(tmp_path):
    c = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    state = c.get('/api/v1/score').json()
    assert state['session'] is None and state['ours'] == 0 and state['can_undo'] is False
