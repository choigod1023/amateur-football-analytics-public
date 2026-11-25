"""P5 of the second rehearsal (2026-11-25): after "새 경기 시작" the bands of the match before (red "분석 프로그램 종료", "하프타임 보고서가 준비되었습니다",
"후반으로 넘어갔습니다 … 확인했음") are not shown any more. Nothing is deleted, and a new match whose analysis has not started is not an alarm.
When the analysis of the new match starts and then stops, the red band comes back as before."""
import json
import os
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import service_routes


def alerts(store, session, pid, wall, seconds=30):
    folder = store / 'alerts' / session
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / 'alerts.jsonl', 'a', encoding='utf-8') as handle:
        for t in range(0, seconds, 5):
            handle.write(json.dumps({'time': float(t), 'kind': 'heartbeat', 'type': 'heartbeat', 'polarity': 'status', 'pid': pid, 'wall': wall + t}) + '\n')
    return folder / 'alerts.jsonl'


def start_match(store, name, created):
    folder = store / 'service' / 'setup'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'match.json').write_text(json.dumps({'name': name, 'created': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(created))}), encoding='utf-8')


def test_the_bands_of_the_match_before_go_away_with_a_new_match_and_come_back_for_the_new_one(tmp_path):
    store = tmp_path
    web = tmp_path / 'web'
    web.mkdir()
    app = FastAPI()
    watch, halftime = service_routes.install(app, store, web, start_thread=False)
    living = {222}
    watch.pid_check = lambda pid: pid in living
    client = TestClient(app)
    old_wall = time.time() - 600
    start_match(store, 'rehearsal3-20261125', old_wall - 60)
    path = alerts(store, 'rehearsal3-20261125', 111, old_wall)                         # its process (111) has ended: red band
    os.utime(path, (old_wall + 30, old_wall + 30))
    folder = store / 'service' / 'halftime' / 'rehearsal3-20261125'
    folder.mkdir(parents=True)
    (folder / 'state.json').write_text(json.dumps({'status': 'ready', 'source': 'coach', 'end_s': 227.2, 'end_text': '3분 47초',
                                                   'second_half': {'at_text': '01:58:45', 'direction': -1, 'colour_checked': False, 'attack_text': '화면 왼쪽'}}), encoding='utf-8')
    service = client.get('/api/v1/service').json()
    half = client.get('/api/v1/halftime').json()
    assert service['state'] == 'down' and service['cause'] == 'process_dead'
    assert half['status'] == 'ready' and half['second_half']['colour_checked'] is False      # the two yellow bands of the old match

    start_match(store, 'rehearsal4-20261125', time.time() - 1)                             # "새 경기 시작"
    service = client.get('/api/v1/service').json()
    half = client.get('/api/v1/halftime').json()
    assert service['state'] == 'idle' and service['session'] is None and 'headline' in service and service['headline'] != '분석 프로그램 종료'
    assert half['session'] is None and half['status'] == 'waiting' and 'second_half' not in half
    assert path.is_file() and (folder / 'state.json').is_file()                            # nothing deleted
    assert any(o['session'] == 'rehearsal3-20261125' for o in service['outages'])          # the log of stops keeps the old one

    # the new match's analysis starts (process 222), then ends: the red band is shown again, for the new match
    alerts(store, 'rehearsal4-20261125', 222, time.time() - 30)
    service = client.get('/api/v1/service').json()
    assert service['state'] == 'ok' and service['session'] == 'rehearsal4-20261125'
    living.clear()
    service = client.get('/api/v1/service').json()
    assert service['state'] == 'down' and service['cause'] == 'process_dead' and service['session'] == 'rehearsal4-20261125'
    assert client.get('/api/v1/halftime').json()['session'] == 'rehearsal4-20261125'


def test_without_a_match_of_setup_the_newest_session_is_watched_as_before(tmp_path):
    app = FastAPI()
    watch, _ = service_routes.install(app, tmp_path, tmp_path, start_thread=False)
    watch.pid_check = lambda pid: False
    alerts(tmp_path, 'match-a', 5, time.time() - 30)
    state = TestClient(app).get('/api/v1/service').json()
    assert state['state'] == 'down' and state['session'] == 'match-a'
