import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import setup_routes
from app.setup_routes import Processes, analysis_command, install, own_counts, reader_mode, run_folder

H = {}

# The "새 팀 판별 명령" of work/match-commands-20261125.md section 4 (copied on 2026-11-24, the PowerShell "*> run.log" left out).
SHEET = ('scripts\\run_live_feedback.py rtsp://127.0.0.1:18554/match ..\\..\\work\\venue-1120\\calibrations.json cam4 --direction 1 --team B '
         '--detector ..\\..\\work\\detector-ft-20261112\\ft_n2\\best.pt --detector-half --detector-batch 8 --link-team-gate --mark-keeper-zone '
         '--reconnect-max-seconds 2 --reconnect-give-up-seconds 1200 --small-box-team 0.6 --small-box-team-all --team-vote-switch 4 --pitch-margin -1.5 --neon-band 30 70 '
         '--dark-min 0.15 --vote-min 2 --team-profile ..\\..\\work\\human-labels\\public-own-match-review-20261111\\service\\team_profile.json '
         '--store ..\\..\\work\\human-labels\\public-own-match-review-20261111 --session match-20261125 '
         '--positions ..\\..\\work\\human-labels\\public-own-match-review-20261111\\alerts\\match-20261125\\positions.jsonl '
         '--frames-log ..\\..\\work\\live-run-1125\\frames.jsonl --heartbeat-seconds 5 --device 0')


class FakeProcs(Processes):
    def __init__(self):
        self.running = {}                 # pid -> kind
        self.external = []
        self.launched = []
        self.next_pid = 1000
        self.commands = {}                # pid -> command line
        self.killed = []
        super().__init__(scan=self._fake_scan, launch=self._fake_launch, alive=lambda pid, ct: pid in self.running, kill=self._fake_kill,
                         cmdline=lambda pid: self.commands.get(pid) if pid in self.running else None)

    def _fake_scan(self):
        return [{'kind': kind, 'pid': pid, 'create_time': 1.0, 'args': self.commands.get(pid)} for pid, kind in self.running.items()] + list(self.external)

    def _fake_launch(self, command, log_path, cwd):
        self.next_pid += 1
        kind = 'run' if 'run_live_feedback.py' in command[1] else 'prepare'
        self.running[self.next_pid] = kind
        self.commands[self.next_pid] = list(command)
        self.launched.append((command, Path(log_path)))
        return {'pid': self.next_pid, 'create_time': 1.0}

    def _fake_kill(self, pid, create_time):
        self.killed.append(pid)
        return self.running.pop(pid, None) is not None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('FOOTBALL_SETUP_RUN_ROOT', str(tmp_path / 'work'))
    store = tmp_path / 'store'
    (store / 'service').mkdir(parents=True)
    web = tmp_path / 'web'
    web.mkdir()
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'yolo11n.pt').write_bytes(b'x')
    monkeypatch.setattr(setup_routes, 'REPO', repo)
    procs = FakeProcs()
    world = {'frame': b'\xff\xd8x\xff\xd9', 'receiver': True, 'memory': (20.0, 9.0)}
    app = FastAPI()
    install(app, store, web, processes=procs, frame_source=lambda: world['frame'], memory=lambda: world['memory'], receiver_check=lambda: world['receiver'])
    client = TestClient(app)
    return client, store, procs, world


def new_match(client, name='match-20261125'):
    return client.post('/api/v1/setup/match', json={'name': name, 'confirm': name[-4:]}, headers=H)


def choose_colours(store, created=None):
    profile = {'version': 1, 'created': created or time.strftime('%Y-%m-%dT%H:%M:%S'), 'own': {'centre': [50, 0, 0]}, 'opponent': {'centre': [50, 10, 10]}, 'note': '우리 팀은 초록 옷'}
    (store / 'service' / 'team_profile.json').write_text(json.dumps(profile), encoding='utf-8')


def wait_frame(client):
    for _ in range(50):
        if client.get('/api/v1/setup').json()['video']['state'] == 'ok':
            return
        time.sleep(0.05)


def actions(store):
    path = store / 'service' / 'setup' / 'actions.jsonl'
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.is_file() else []


def test_new_match_and_stop_need_the_last_four_characters(env):
    client, store, procs, _ = env
    reply = client.post('/api/v1/setup/match', json={'name': 'match-20261125'}, headers=H)
    assert reply.status_code == 400 and '1125' in reply.json()['detail']
    assert client.post('/api/v1/setup/match', json={'name': 'match-20261125', 'confirm': '1124'}, headers=H).status_code == 400
    assert not (store / 'service' / 'setup' / 'match.json').exists()
    assert new_match(client).status_code == 200
    choose_colours(store)
    assert client.post('/api/v1/setup/start', json={'direction': 1}, headers=H).status_code == 200
    assert client.post('/api/v1/setup/stop', json={}, headers=H).status_code == 400
    assert client.post('/api/v1/setup/stop', json={'confirm': '0000'}, headers=H).status_code == 400
    assert procs.running                                                            # still running
    assert client.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H).json() == {'stopped': 1}
    log = actions(store)
    assert [r['action'] for r in log if r['result'] == 'ok'] == ['match_new', 'start', 'stop']
    assert all(r['client'] == 'testclient' and r['at'] for r in log)
    assert sum(r['result'] == 'refused' for r in log) == 4


def test_start_refused_without_video(env):
    client, store, procs, world = env
    new_match(client)
    choose_colours(store)
    world['frame'] = None
    reply = client.post('/api/v1/setup/start', json={'direction': 1}, headers=H)
    assert reply.status_code == 409 and '영상' in reply.json()['detail'] and procs.launched == []


def test_repeated_start_requests_are_refused(env):
    client, store, procs, world = env
    new_match(client)
    choose_colours(store)
    world['frame'] = None                                                           # each try is counted, then refused for the video
    codes = [client.post('/api/v1/setup/start', json={'direction': 1}, headers=H).status_code for _ in range(setup_routes.START_LIMIT + 2)]
    assert codes[:setup_routes.START_LIMIT] == [409] * setup_routes.START_LIMIT and codes[setup_routes.START_LIMIT:] == [429, 429]
    world['frame'] = b'\xff\xd8x\xff\xd9'
    assert client.post('/api/v1/setup/start', json={'direction': 1}, headers=H).status_code == 429
    assert procs.launched == []


def test_double_press_starts_one_run(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    first = client.post('/api/v1/setup/start', json={'direction': 1}, headers=H)
    second = client.post('/api/v1/setup/start', json={'direction': 1}, headers=H)
    assert first.status_code == 200 and second.status_code == 409 and len(procs.running) == 1


def test_restart_after_a_stop_or_a_death_goes_on_with_the_same_session(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={'direction': -1}, headers=H)
    client.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H)
    state = client.get('/api/v1/setup').json()['analysis']
    assert state['ended'] == 'stopped' and state['restart_direction'] == -1
    assert client.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200
    command, _ = procs.launched[-1]
    assert command[command.index('--session') + 1] == 'match-20261125' and command[command.index('--direction') + 1] == '-1'
    # the run dies by itself after the second half was switched: the restart takes the second-half direction and notes the death once
    (store / 'alerts' / 'match-20261125' / 'control.jsonl').write_text('{"seq": 1, "cmd": "second_half", "direction": 1, "at": 1.0}\n', encoding='utf-8')
    procs.running.clear()
    state = client.get('/api/v1/setup').json()['analysis']
    client.get('/api/v1/setup')
    assert state['ended'] == 'died' and state['restart_direction'] == 1
    assert sum(r['action'] == 'run_died' for r in actions(store)) == 1
    assert client.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200
    command, _ = procs.launched[-1]
    assert command[command.index('--session') + 1] == 'match-20261125' and command[command.index('--direction') + 1] == '1'
    assert client.post('/api/v1/setup/restart', json={}, headers=H).status_code == 409    # already running again


def test_colour_choice_is_told_in_the_words_of_this_page(env):
    client, store, *_ = env
    new_match(client)
    choose_colours(store)
    profile = json.loads((store / 'service' / 'team_profile.json').read_text(encoding='utf-8'))
    profile['note'] = '우리 팀은 사진 오른쪽 어두운 회색 옷 팀입니다.'                 # the sentence app/team_select_routes.py saves
    (store / 'service' / 'team_profile.json').write_text(json.dumps(profile, ensure_ascii=False), encoding='utf-8')
    assert client.get('/api/v1/setup').json()['colours']['text'] == '우리 팀은 둘째 묶음 어두운 회색 옷 팀입니다.'


def write_candidates(store, people=(9, 8), created=None):
    folder = store / 'service' / 'team_select'
    folder.mkdir(parents=True, exist_ok=True)
    groups = [{'colour_text': '초록', 'people': people[0], 'images': ['g0_0.jpg']}, {'colour_text': '빨강', 'people': people[1], 'images': ['g1_0.jpg']}]
    (folder / 'candidates.json').write_text(json.dumps({'created': created or time.strftime('%Y-%m-%dT%H:%M:%S'), 'ok': True, 'weak': False, 'groups': groups}), encoding='utf-8')


def test_few_people_in_a_colour_group_asks_for_new_pictures(env):
    client, store, *_ = env
    new_match(client)
    write_candidates(store, (4, 13))
    colours = client.get('/api/v1/setup').json()['colours']
    assert colours['state'] == 'choose' and colours['few_people'] is True and colours['fewest'] == 4
    write_candidates(store, (setup_routes.FEW_PICTURE_PEOPLE, 13))
    assert client.get('/api/v1/setup').json()['colours']['few_people'] is False


def test_new_pictures_after_the_choice_must_be_chosen_before_a_restart(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={'direction': 1}, headers=H)
    client.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H)
    time.sleep(1.1)                                                                   # pictures made a second later than the choice
    write_candidates(store, (9, 8))
    state = client.get('/api/v1/setup').json()
    assert state['colours']['state'] == 'choose' and state['analysis']['ended'] == 'stopped'
    reply = client.post('/api/v1/setup/restart', json={}, headers=H)
    assert reply.status_code == 409 and '새 사진' in reply.json()['detail'] and len(procs.launched) == 1
    time.sleep(1.1)
    choose_colours(store)                                                             # the new choice
    assert client.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200


def test_restart_without_an_earlier_run_is_refused(env):
    client, store, procs, _ = env
    new_match(client)
    assert client.post('/api/v1/setup/restart', json={}, headers=H).status_code == 409


@pytest.mark.parametrize('name', ['../x', 'Match-1', 'label-20261125', '_old', 'a', 'match 1', 'x' * 41, 'match/1'])
def test_match_name_is_checked(env, name):
    client, store, *_ = env
    assert new_match(client, name).status_code in (400, 422)
    assert not (store / 'service' / 'setup' / 'match.json').exists()


def test_new_match_moves_the_last_match_away_and_never_deletes(env):
    client, store, procs, _ = env
    old_session = store / 'alerts' / 'match-20261120'
    old_session.mkdir(parents=True)
    (old_session / 'score.jsonl').write_text('{"id": 0, "kind": "goal", "team": "ours"}\n', encoding='utf-8')
    (store / 'service' / 'team_select').mkdir()
    (store / 'service' / 'team_select' / 'candidates.json').write_text('{"created": "2026-11-20T19:00:00"}', encoding='utf-8')
    choose_colours(store, '2026-11-20T19:05:00')
    reply = new_match(client)
    assert reply.status_code == 200, reply.text
    assert set(reply.json()['moved']) == {'team_profile.json', 'team_select'}
    archive = store / 'service' / '_archive' / reply.json()['match']['archive']
    assert (archive / 'team_profile.json').is_file() and (archive / 'team_select' / 'candidates.json').is_file()
    assert not (store / 'service' / 'team_profile.json').exists()
    assert (old_session / 'score.jsonl').is_file()                                  # the old match keeps its score file
    assert not (store / 'alerts' / 'match-20261125' / 'score.jsonl').exists()        # the new one starts at 0 : 0
    state = client.get('/api/v1/setup').json()
    assert state['match']['name'] == 'match-20261125' and state['colours']['state'] == 'start'
    # the same name again: refused, nothing moves, nothing lost
    choose_colours(store)
    again = new_match(client)
    assert again.status_code == 409 and '이미 있습니다' in again.json()['detail']
    assert (store / 'service' / 'team_profile.json').is_file() and archive.is_dir()
    cont = client.post('/api/v1/setup/match', json={'name': 'match-20261125', 'mode': 'continue'}, headers=H)
    assert cont.status_code == 200 and cont.json()['moved'] == []
    assert client.get('/api/v1/setup').json()['colours']['state'] == 'ok'


def test_start_needs_a_colour_choice_made_for_this_match(env):
    client, store, procs, _ = env
    choose_colours(store, '2026-11-20T19:05:00')
    profile = store / 'service' / 'team_profile.json'
    new_match(client)
    profile.parent.mkdir(exist_ok=True)
    choose_colours(store, '2026-11-20T19:05:00')                                     # an old choice put back: still refused
    reply = client.post('/api/v1/setup/start', json={'direction': 1}, headers=H)
    assert reply.status_code == 409 and '팀 색' in reply.json()['detail'] and procs.launched == []
    choose_colours(store)
    assert client.post('/api/v1/setup/start', json={'direction': 1}, headers=H).status_code == 200
    assert len(procs.launched) == 1


def test_only_one_run_at_a_time(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    assert client.post('/api/v1/setup/start', json={'direction': -1}, headers=H).status_code == 200
    second = client.post('/api/v1/setup/start', json={'direction': -1}, headers=H)
    assert second.status_code == 409 and len(procs.launched) == 1
    assert client.post('/api/v1/setup/team-photos', json={}, headers=H).status_code == 409
    assert new_match(client, 'match-other').status_code == 409                         # no new match while a run goes on
    assert client.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H).json() == {'stopped': 1}
    assert not procs.running
    procs.external.append({'kind': 'run', 'pid': 42, 'create_time': 3.0})            # a run started from a terminal
    assert client.post('/api/v1/setup/start', json={'direction': 1}, headers=H).status_code == 409
    assert len(procs.launched) == 1


def test_start_refused_without_receiver_or_memory_and_bad_direction(env):
    client, store, procs, world = env
    new_match(client)
    choose_colours(store)
    assert client.post('/api/v1/setup/start', json={'direction': 0}, headers=H).status_code == 400
    world['receiver'] = False
    assert client.post('/api/v1/setup/start', json={'direction': 1}, headers=H).status_code == 409
    world['receiver'] = True
    world['memory'] = (3.0, 9.0)
    assert client.post('/api/v1/setup/start', json={'direction': 1}, headers=H).status_code == 409
    assert client.get('/api/v1/setup').json()['memory']['state'] == 'block'
    world['memory'] = (8.0, 9.0)
    assert client.get('/api/v1/setup').json()['memory']['state'] == 'low'
    assert procs.launched == []


def test_command_matches_the_match_day_sheet_option_for_option(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={'direction': 1}, headers=H)
    command, log = procs.launched[0]
    sheet = SHEET.split()
    ours = command[1:]
    assert len(ours) == len(sheet)
    for mine, theirs in zip(ours, sheet):
        if '\\' in theirs or '/' in theirs:                                          # paths: same file name, the folders differ (absolute, test store)
            assert Path(mine.replace('\\', '/')).name == Path(theirs.replace('\\', '/')).name or theirs.endswith('human-labels\\public-own-match-review-20261111')
        else:
            assert mine == theirs
    assert log == run_folder(Path(store).parent / 'work', 'match-20261125') / 'run.log'
    assert log.parent.name == 'live-run-1125'
    assert command[command.index('--positions') + 1] == str(store / 'alerts' / 'match-20261125' / 'positions.jsonl')
    assert command[command.index('--team-profile') + 1] == str(store / 'service' / 'team_profile.json')


def test_analysis_command_changes_only_session_and_direction():
    a = analysis_command('C:/s', 'match-20261125', 1)
    b = analysis_command('C:/s', 'test-1', -1)
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    assert len(a) == len(b) and all('match-20261125' in x or x == '1' or 'live-run-1125' in x for x, _ in diff)


def test_state_reads_the_reader_line_and_the_own_count(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={'direction': 1}, headers=H)
    _, log = procs.launched[0]
    profile = json.loads((store / 'service' / 'team_profile.json').read_text(encoding='utf-8'))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(f"Team colours from the coach's choice ({profile['created']}): own team x.\nSmall-box team reader OFF: hue gap 4.8 deg < 50\n", encoding='utf-8')
    positions = store / 'alerts' / 'match-20261125' / 'positions.jsonl'
    rows = [{'type': 'header'}] + [{'type': 'second', 'time': t, 'team': [[i, 0, 0] for i in range(8 if t % 2 else 9)], 'other': []} for t in range(70)]
    positions.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
    state = client.get('/api/v1/setup').json()
    assert state['analysis']['running'] is True and state['analysis']['direction'] == 1
    check = state['check']
    assert check['reader'] == 'off' and check['reader_text'] == '기본 방식으로 구분 중' and check['colours_today'] is True
    assert check['own_now'] == 8 and check['own_mean'] == 8.5 and check['seconds'] == 60


def test_state_of_the_video_and_the_colour_pictures(env):
    client, store, procs, world = env
    world['frame'] = None
    state = client.get('/api/v1/setup').json()
    assert state['video']['state'] == 'wait' and '송출을 시작하세요' in state['video']['text']
    world['receiver'] = False
    assert client.get('/api/v1/setup').json()['video']['state'] == 'problem'
    world['receiver'], world['frame'] = True, b'\xff\xd8x\xff\xd9'
    setup_routes.FRAME_EVERY = 0.0
    try:
        wait_frame(client)
    finally:
        setup_routes.FRAME_EVERY = 6.0
    assert client.get('/api/v1/setup').json()['video']['state'] == 'ok'
    new_match(client)
    assert client.post('/api/v1/setup/team-photos', json={}, headers=H).json() == {'started': True}
    assert client.get('/api/v1/setup').json()['colours']['state'] == 'making'
    assert client.post('/api/v1/setup/team-photos', json={}, headers=H).json() == {'started': False, 'running': True}
    command, log = procs.launched[0]
    assert command[1:] == ['scripts/team_select_prepare.py', 'rtsp://127.0.0.1:18554/match', '--store', str(store), '--start', '0', '--seconds', '60',
                           '--calibrations', command[10], '--camera', 'cam4', '--pitch-margin', '0', '--groups', '2', '--retakes', '2']   # 2026-11-25 colour pick
    procs.running.clear()
    folder = store / 'service' / 'team_select'
    folder.mkdir(parents=True)
    (folder / 'candidates.json').write_text(json.dumps({'created': time.strftime('%Y-%m-%dT%H:%M:%S'), 'ok': True, 'weak': False,
                                                        'groups': [{'colour_text': '초록', 'people': 9, 'images': ['g0_0.jpg']}, {'colour_text': '빨강', 'people': 8, 'images': ['g1_0.jpg']}]}), encoding='utf-8')
    colours = client.get('/api/v1/setup').json()['colours']
    assert colours['state'] == 'choose' and colours['groups'][0]['urls'] == ['/team-select-files/g0_0.jpg']


def test_colour_pictures_refused_without_the_detector_file(env):
    client, store, procs, _ = env
    new_match(client)
    (setup_routes.REPO / 'yolo11n.pt').unlink()
    assert client.post('/api/v1/setup/team-photos', json={}, headers=H).status_code == 409
    assert procs.launched == []


def test_lines_answer_is_kept_per_match(env):
    client, store, *_ = env
    assert client.post('/api/v1/setup/lines', json={'answer': 'ok'}, headers=H).status_code == 409
    new_match(client)
    assert client.post('/api/v1/setup/lines', json={'answer': 'maybe'}, headers=H).status_code == 400
    assert client.post('/api/v1/setup/lines', json={'answer': 'bad'}, headers=H).status_code == 200
    assert client.get('/api/v1/setup').json()['lines']['answer'] == 'bad'


def test_helpers(tmp_path):
    assert reader_mode('x\nSmall-box team reader ON: hue gap 100.8 deg') == 'on'
    assert reader_mode('nothing') is None
    assert own_counts(tmp_path / 'none.jsonl') == (None, None, 0)
    assert run_folder('W', 'match-20261125').name == 'live-run-1125' and run_folder('W', 'sim-a').name == 'live-run-sim-a'


def test_page_is_served_by_the_review_server(tmp_path, monkeypatch):
    from app.review_public import create_app
    monkeypatch.delenv('FOOTBALL_SETUP_TOKEN', raising=False)
    monkeypatch.setenv('LIVE_VIDEO_URL', 'rtsp://127.0.0.1:9/none')                 # never ask the real receiver from a test
    monkeypatch.setattr(setup_routes, 'grab_frame', lambda source, timeout=12.0: None)   # and start no ffmpeg that could outlive the test
    origin = 'http://review.test:8443'
    client = TestClient(create_app(tmp_path, origin), base_url=origin)
    page = client.get('/setup')
    assert page.status_code == 200 and '경기 준비' in page.text
    assert client.get('/setup.js').status_code == 200 and client.get('/setup.css').status_code == 200
    assert client.get('/api/v1/setup').json()['match'] is None
    reply = client.post('/api/v1/setup/start', json={'direction': 1}, headers={'Origin': origin, **H})
    assert reply.status_code == 409 and '새 경기' in reply.json()['detail']
    assert client.post('/api/v1/setup/start', json={'direction': 1}, headers={'Origin': 'http://evil.example', **H}).status_code == 403
