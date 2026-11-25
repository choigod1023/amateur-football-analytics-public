"""The warm-up procedure of /setup (2026-11-25): temporary direction, direction and colour choice just before the kickoff, automatic restart."""
import json
import time

from app import setup_routes
from tests.test_setup_routes import H, choose_colours, env, new_match, write_candidates  # noqa: F401  (env is a fixture)


def positions_file(store, session='match-20261125'):
    return store / 'alerts' / session / 'positions.jsonl'


def write_second(store, session='match-20261125', direction=-1):
    path = positions_file(store, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'type': 'header', 'team': 'B', 'other': 'A', 'direction': direction, 'pitch_length': 89.0, 'pitch_width': 62.0, 'first_second': 0.0}) + '\n'
                    + json.dumps({'type': 'second', 'time': 1, 'team': [[1, 1.0, 1.0]] * 9, 'other': []}) + '\n', encoding='utf-8')


def mark_kickoff(store):
    folder = store / 'analyst-tags'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'tags.jsonl').write_text(json.dumps({'op': 'add', 'id': 'a' * 12, 'kind': 'start_h1', 'note': '', 'epoch': time.time()}) + '\n', encoding='utf-8')


def direction_of(command):
    return int(command[command.index('--direction') + 1])


def test_the_warm_up_start_has_no_direction_and_uses_a_temporary_one_that_is_not_confirmed(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    assert client.post('/api/v1/setup/start', json={}, headers=H).status_code == 200
    command = procs.launched[0][0]
    assert direction_of(command) == setup_routes.TEMPORARY_DIRECTION
    assert command[command.index('--reconnect-give-up-seconds') + 1] == '1200'
    state = client.get('/api/v1/setup').json()
    assert state['direction'] == {'value': -1, 'confirmed': False, 'running': -1} and state['clock']['state'] == 'before'


def test_the_same_direction_before_the_kickoff_only_confirms_and_a_new_one_restarts_with_clean_records(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={}, headers=H)
    write_second(store)
    same = client.post('/api/v1/setup/kickoff/direction', json={'direction': -1}, headers=H).json()
    assert same == {'direction': -1, 'restarted': False} and len(procs.launched) == 1
    assert client.get('/api/v1/setup').json()['direction']['confirmed'] is True
    other = client.post('/api/v1/setup/kickoff/direction', json={'direction': 1}, headers=H).json()
    assert other['restarted'] is True and len(procs.launched) == 2 and direction_of(procs.launched[1][0]) == 1
    assert len(procs.running) == 1                                                    # the old run was ended, the new one runs
    assert not positions_file(store).exists()                                         # the warm-up record (first header = old direction) went to the archive
    assert list((store / 'service' / '_archive').glob('*-before-restart-match-20261125/positions.jsonl'))
    assert client.get('/api/v1/setup').json()['direction'] == {'value': 1, 'confirmed': True, 'running': 1}


def test_nothing_before_the_kickoff_can_change_after_the_kickoff(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={}, headers=H)
    mark_kickoff(store)
    assert client.get('/api/v1/setup').json()['clock']['state'] == 'h1'
    for path, body in (('direction', {'direction': 1}), ('recolour', {}), ('colours-keep', {}), ('colours-revert', {})):
        reply = client.post(f'/api/v1/setup/kickoff/{path}', json=body, headers=H)
        assert reply.status_code == 409 and '전반이 이미 시작' in reply.json()['detail']
    assert len(procs.launched) == 1


def test_keeping_the_colours_needs_a_running_analysis_and_is_remembered(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    assert client.post('/api/v1/setup/kickoff/colours-keep', json={}, headers=H).status_code == 409
    client.post('/api/v1/setup/start', json={}, headers=H)
    write_second(store)
    assert client.post('/api/v1/setup/kickoff/colours-keep', json={}, headers=H).json() == {'kept': True}
    assert client.get('/api/v1/setup').json()['colours_kept'] is True


def test_new_colours_restart_the_analysis_by_themselves_and_the_seconds_are_measured(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={'direction': 1}, headers=H)
    write_second(store, direction=1)
    time.sleep(1.1)
    assert client.post('/api/v1/setup/kickoff/recolour', json={}, headers=H).json() == {'started': True}
    assert list(procs.running.values()) == ['prepare']                                # the analysis was stopped for the pictures
    state = client.get('/api/v1/setup').json()
    assert state['job']['phase'] == 'photos' and '약 1분 30초' in state['job']['text']
    assert client.post('/api/v1/setup/kickoff/recolour', json={}, headers=H).json()['started'] is False
    procs.running.clear()                                                             # the picture job ends
    time.sleep(1.1)
    write_candidates(store, (9, 8))
    assert client.get('/api/v1/setup').json()['job']['phase'] == 'choose'
    assert len(procs.launched) == 2                                                   # nothing restarted before the choice
    time.sleep(1.1)
    choose_colours(store)                                                             # the own team is chosen
    state = client.get('/api/v1/setup').json()
    assert state['job']['phase'] == 'starting' and len(procs.launched) == 3
    command = procs.launched[2][0]
    assert 'run_live_feedback.py' in command[1] and direction_of(command) == 1        # same direction as before
    assert not positions_file(store).exists()                                         # the warm-up record with the old colours is archived
    write_second(store, direction=1)                                                  # the new analysis wrote its first second
    state = client.get('/api/v1/setup').json()
    assert state['job']['phase'] == 'done' and isinstance(state['job']['seconds'], int)
    assert json.loads((store / 'service' / 'setup' / 'restart_times.json').read_text(encoding='utf-8')) == [state['job']['seconds']]
    assert client.get('/api/v1/setup').json()['restart_seconds'] == state['job']['seconds']


def test_memory_below_the_project_rule_says_so_in_plain_words_and_still_allows_the_start(env):
    client, store, procs, world = env
    new_match(client)
    choose_colours(store)
    world['memory'] = (11.0, 9.0)
    memory = client.get('/api/v1/setup').json()['memory']
    assert memory['state'] == 'low' and memory['text'] == '메모리 여유가 적습니다(11.0 GB). 분석은 시작할 수 있습니다. 화면이 느려지면 담당자에게 연락하세요.'
    world['memory'] = (20.0, 7.5)
    low = client.get('/api/v1/setup').json()['memory']
    assert low['state'] == 'low' and '(7.5 GB)' in low['text'] and '모자랍니다' not in low['text']
    assert client.post('/api/v1/setup/start', json={}, headers=H).status_code == 200      # the block values (4 GB, 3 GB) did not change
    world['memory'] = (20.0, 8.5)
    assert client.get('/api/v1/setup').json()['memory']['state'] == 'ok'
