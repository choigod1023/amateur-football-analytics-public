"""A new match started on /setup must show 0 : 0 and no alert at once, before the analysis writes its first row (2026-11-24 polish).
The files of the match before stay as they are: score.jsonl is append-only and is never touched here."""
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from app import setup_routes
from app.review_public import create_app

ORIGIN = 'http://127.0.0.1:8443'
H = {'Origin': ORIGIN}


@pytest.fixture(autouse=True)
def no_live_run_on_this_computer(monkeypatch):
    """/setup refuses a new match while an analysis runs on the computer; these tests must not depend on what runs here."""
    monkeypatch.setattr(setup_routes.Processes, '_psutil_scan', staticmethod(lambda: []))


def old_match(tmp_path, name='match-20261124'):
    folder = tmp_path / 'alerts' / name
    folder.mkdir(parents=True)
    rows = [{'time': 5.0, 'kind': 'heartbeat', 'type': 'heartbeat', 'polarity': 'status', 'wall': 1.0},
            {'time': 6.5, 'kind': 'box_attack', 'polarity': 'poor', 'title': 'Old alert', 'text': 'from the match before'}]
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
    goals = [{'id': 0, 't': 1.0, 'utc': 'x', 'kind': 'goal', 'team': 'ours', 'source': 'manual', 'analysis': None},
             {'id': 1, 't': 20.0, 'utc': 'x', 'kind': 'goal', 'team': 'ours', 'source': 'manual', 'analysis': None},
             {'id': 2, 't': 40.0, 'utc': 'x', 'kind': 'goal', 'team': 'opp', 'source': 'manual', 'analysis': None}]
    (folder / 'score.jsonl').write_text('\n'.join(json.dumps(g) for g in goals) + '\n', encoding='utf-8')
    past = time.time() - 3600                                  # the match before ended an hour ago
    for name_ in ('alerts.jsonl', 'score.jsonl'):
        os.utime(folder / name_, (past, past))
    return folder


def test_new_match_shows_zero_and_no_alert_until_the_analysis_writes(tmp_path):
    old = old_match(tmp_path)
    before = (old / 'score.jsonl').read_bytes()
    c = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    assert c.get('/api/v1/score').json()['ours'] == 2          # the match before is the live one until a new match is started
    assert c.get('/api/v1/bench').json()['current']['title'] == 'Old alert'
    made = c.post('/api/v1/setup/match', json={'name': 'match-20261125', 'confirm': '1125'}, headers=H)
    assert made.status_code == 200
    score = c.get('/api/v1/score').json()
    assert (score['ours'], score['opp'], score['pending']) == (0, 0, [])
    bench = c.get('/api/v1/bench').json()
    assert bench['current'] is None and bench['recent'] == []
    assert (old / 'score.jsonl').read_bytes() == before        # the match before is byte for byte as it was
    assert (old / 'alerts.jsonl').is_file()
    # one press in the new match: 1 : 0, written to the new match only
    assert score['session'] == 'match-20261125'
    pressed = c.post('/api/v1/score', json={'session': score['session'], 'kind': 'goal', 'team': 'ours', 'source': 'manual'}, headers=H)
    assert pressed.status_code == 200
    assert (pressed.json()['ours'], pressed.json()['opp']) == (1, 0)
    assert c.get('/api/v1/score').json()['ours'] == 1
    assert (old / 'score.jsonl').read_bytes() == before


def test_the_analysis_of_the_new_match_takes_over_when_it_writes(tmp_path):
    old_match(tmp_path)
    c = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    c.post('/api/v1/setup/match', json={'name': 'match-20261125', 'confirm': '1125'}, headers=H)
    folder = tmp_path / 'alerts' / 'match-20261125'
    (folder / 'alerts.jsonl').write_text(json.dumps({'time': 1.0, 'kind': 'box_attack', 'title': 'New alert', 'text': 'now'}) + '\n', encoding='utf-8')
    assert c.get('/api/v1/bench').json()['current']['title'] == 'New alert'
    assert c.get('/api/v1/score').json()['session'] == 'match-20261125'


def test_a_run_started_by_hand_under_another_name_is_still_shown(tmp_path):
    old_match(tmp_path)
    c = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    c.post('/api/v1/setup/match', json={'name': 'match-20261125', 'confirm': '1125'}, headers=H)
    time.sleep(1.1)                                             # the match record has second resolution
    other = tmp_path / 'alerts' / 'hand-run'
    other.mkdir()
    (other / 'alerts.jsonl').write_text(json.dumps({'time': 1.0, 'kind': 'box_attack', 'title': 'Hand alert', 'text': 'x'}) + '\n', encoding='utf-8')
    assert c.get('/api/v1/bench').json()['current']['title'] == 'Hand alert'
    assert c.get('/api/v1/score').json()['session'] == 'hand-run'


def test_continuing_the_old_match_shows_its_score_again(tmp_path):
    old_match(tmp_path)
    c = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    c.post('/api/v1/setup/match', json={'name': 'match-20261125', 'confirm': '1125'}, headers=H)
    assert c.post('/api/v1/setup/match', json={'name': 'match-20261124', 'mode': 'continue'}, headers=H).status_code == 200
    assert c.get('/api/v1/score').json()['ours'] == 2
    assert c.get('/api/v1/bench').json()['current']['title'] == 'Old alert'
