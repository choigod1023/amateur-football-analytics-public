"""P1 of the second rehearsal (2026-11-25 01:14-02:11): a review server ends only the analysis it started itself.

The rehearsal's analysis ended silently six times: a test server on port 8473 (another store) pressed the direction step of /setup, and stop_current() ended every
run_live_feedback.py on the computer (work/overnight-1124/night-ui/server-*.err.log, setup_direction line 996, at 01:23:51 ... 01:59:51).
Here two servers share one process table (one computer) and must never end each other's analysis; another analysis only blocks a start (one GPU analysis at a time)."""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import setup_routes
from app.setup_routes import OTHER_RUN_TEXT, command_belongs, install
from tests.test_setup_routes import H, FakeProcs, choose_colours, new_match


class Computer:
    """One process table seen by every server of the test."""
    def __init__(self):
        self.running, self.commands, self.external, self.killed = {}, {}, [], []


def shared(computer, first_pid):
    procs = FakeProcs()
    procs.running, procs.commands, procs.external, procs.killed = computer.running, computer.commands, computer.external, computer.killed
    procs.next_pid = first_pid
    return procs


def server(tmp_path, computer, name, first_pid):
    store = tmp_path / name
    (store / 'service').mkdir(parents=True, exist_ok=True)
    web = tmp_path / 'web'
    web.mkdir(exist_ok=True)
    procs = shared(computer, first_pid)
    app = FastAPI()
    install(app, store, web, processes=procs, frame_source=lambda: b'\xff\xd8x\xff\xd9', memory=lambda: (20.0, 9.0), receiver_check=lambda: True)
    return TestClient(app), store, procs


@pytest.fixture
def two(tmp_path, monkeypatch):
    monkeypatch.setenv('FOOTBALL_SETUP_RUN_ROOT', str(tmp_path / 'work'))
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'yolo11n.pt').write_bytes(b'x')
    monkeypatch.setattr(setup_routes, 'REPO', repo)
    computer = Computer()
    a = server(tmp_path, computer, 'store', 1000)          # the match server
    b = server(tmp_path, computer, 'store2', 5000)         # a test server; its store name starts with the other's on purpose
    return computer, a, b


def started(client, store, name='match-20261125'):
    assert new_match(client, name).status_code == 200
    choose_colours(store)
    reply = client.post('/api/v1/setup/start', json={'direction': -1}, headers=H)
    assert reply.status_code == 200, reply.text
    return reply


def test_another_server_never_ends_the_analysis_and_cannot_start_a_second_one(two):
    computer, (ca, sa, pa), (cb, sb, pb) = two
    started(ca, sa)
    mine = next(iter(computer.running))
    assert new_match(cb, 'match-test8473').status_code == 200                       # a new match on the other store does not touch anything
    choose_colours(sb)
    # the rehearsal's case: the test server has no analysis of its own and presses the direction step
    assert cb.post('/api/v1/setup/kickoff/direction', json={'direction': 1}, headers=H).json() == {'direction': 1, 'restarted': False}
    reply = cb.post('/api/v1/setup/start', json={'direction': 1}, headers=H)
    assert reply.status_code == 409 and reply.json()['detail'] == OTHER_RUN_TEXT
    assert cb.post('/api/v1/setup/kickoff/recolour', json={}, headers=H).json()['detail'] == OTHER_RUN_TEXT
    assert cb.post('/api/v1/setup/team-photos', json={}, headers=H).json()['detail'] == OTHER_RUN_TEXT
    assert cb.post('/api/v1/setup/restart', json={}, headers=H).status_code == 409
    stop = cb.post('/api/v1/setup/stop', json={'confirm': '8473'}, headers=H)
    assert stop.status_code == 409 and stop.json()['detail'] == OTHER_RUN_TEXT
    state = cb.get('/api/v1/setup').json()['analysis']
    assert state['running'] is True and state['mine'] is False and state['other'] is True and state['text'] == OTHER_RUN_TEXT
    assert mine in computer.running and computer.killed == []                     # never ended once
    # the match server still stops and starts its own analysis as before
    assert ca.get('/api/v1/setup').json()['analysis']['mine'] is True
    assert ca.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H).json() == {'stopped': 1}
    assert computer.killed == [mine]
    assert ca.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200


def test_the_direction_restart_of_one_server_leaves_the_other_alone(two):
    computer, (ca, sa, pa), (cb, sb, pb) = two
    started(ca, sa)
    theirs = next(iter(computer.running))
    pb.external.clear()
    # the other server had its own analysis before (stopped), so a 'run' record exists there too
    started_b = new_match(cb, 'match-test8473')
    assert started_b.status_code == 200
    choose_colours(sb)
    before = len(pa.launched)
    reply = cb.post('/api/v1/setup/kickoff/direction', json={'direction': 1}, headers=H)
    assert reply.status_code == 200 and reply.json()['restarted'] is False and len(pa.launched) == before
    assert theirs in computer.running and computer.killed == []
    # the match server turns its own analysis round: only its own process is ended, the new one starts
    reply = ca.post('/api/v1/setup/kickoff/direction', json={'direction': 1}, headers=H)
    assert reply.status_code == 200 and reply.json()['restarted'] is True and computer.killed == [theirs]


def test_a_restarted_server_still_ends_its_own_analysis(two, tmp_path):
    computer, (ca, sa, pa), _ = two
    started(ca, sa)
    mine = next(iter(computer.running))
    again, store, _ = server(tmp_path, computer, 'store', 9000)                     # the review server was started again: only run.json is left
    assert again.get('/api/v1/setup').json()['analysis']['mine'] is True
    assert again.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H).json() == {'stopped': 1}
    assert computer.killed == [mine]


def test_a_dead_analysis_is_not_ended_and_can_start_again(two):
    computer, (ca, sa, pa), _ = two
    started(ca, sa)
    computer.running.clear()                                                          # it died
    assert ca.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H).json() == {'stopped': 0}
    assert ca.get('/api/v1/setup').json()['analysis']['ended'] == 'died'
    assert ca.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200
    assert computer.killed == []


def test_a_process_number_used_again_by_another_program_is_not_ended(two):
    computer, (ca, sa, pa), _ = two
    started(ca, sa)
    pid = next(iter(computer.running))
    computer.running[pid] = 'other'                                                   # the run died, Windows gave its number to another program (same start time in the fake)
    computer.commands[pid] = ['C:/Windows/notepad.exe']
    state = ca.get('/api/v1/setup').json()['analysis']
    assert state['mine'] is False and state['running'] is False and state['ended'] == 'died'
    assert ca.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H).json() == {'stopped': 0}
    assert ca.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200
    assert computer.killed == [] and computer.running[pid] == 'other'


def test_a_number_used_again_by_another_servers_run_is_not_ended(two):
    computer, (ca, sa, pa), (cb, sb, pb) = two
    started(ca, sa)
    pid = next(iter(computer.running))
    other_store = sb
    computer.commands[pid] = [c if c != str(sa) else str(other_store) for c in computer.commands[pid]]   # same number, another store's command line
    state = ca.get('/api/v1/setup').json()['analysis']
    assert state['mine'] is False and state['other'] is True
    assert ca.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H).status_code == 409
    assert computer.killed == []


def test_the_child_of_the_own_run_is_not_another_analysis(two):
    """The venv python.exe starts the real python as a child with the same command line (rehearsal procwatch: two numbers per run)."""
    computer, (ca, sa, pa), _ = two
    started(ca, sa)
    parent = next(iter(computer.running))
    computer.external.append({'kind': 'run', 'pid': 77, 'ppid': parent, 'create_time': 1.0, 'args': computer.commands[parent]})
    state = ca.get('/api/v1/setup').json()['analysis']
    assert state['mine'] is True and not state.get('other')


def test_a_terminal_run_on_the_same_store_still_holds_the_match(two):
    computer, (ca, sa, pa), _ = two
    assert new_match(ca).status_code == 200
    computer.external.append({'kind': 'run', 'pid': 42, 'create_time': 3.0, 'args': ['python', 'scripts/run_live_feedback.py', '--store', str(sa)]})
    assert new_match(ca, 'match-other').status_code == 409
    computer.external[:] = [{'kind': 'run', 'pid': 42, 'create_time': 3.0, 'args': ['python', 'scripts/run_live_feedback.py', '--store', str(sa) + '2']}]
    assert new_match(ca, 'match-other').status_code == 200


def test_command_belongs_checks_the_store_and_the_run_folder_exactly(tmp_path):
    store = tmp_path / 'store'
    folder = tmp_path / 'work' / 'live-run-1125'
    args = ['py', 'scripts/run_live_feedback.py', '--store', str(store), '--frames-log', str(folder / 'frames.jsonl')]
    assert command_belongs(args, store, folder) is True
    assert command_belongs(args, store) is True
    assert command_belongs(args, tmp_path / 'stor') is False and command_belongs(args, tmp_path / 'store2') is False
    assert command_belongs(args, store, tmp_path / 'work' / 'live-run-112') is False
    assert command_belongs([a.replace('\\', '/').upper() if '--' not in a else a for a in args], store, folder) is True   # Windows paths: case and slashes
    assert command_belongs(None, store) is None
    assert Path(args[3]).name == 'store'
