"""P6 of the second rehearsal (2026-11-25): the page said "about 60 seconds" for a restart that took 4 to 9 s (3 restarts). The default was 60 and only the automatic
restarts (new colours, new direction) were measured, so the red band's and /setup's restarts never changed it. Now every start of this server is measured."""
import json
from pathlib import Path

from app import setup_routes
from tests.test_setup_routes import H, choose_colours, env, new_match  # noqa: F401  (env is a fixture)

WEB = Path(setup_routes.__file__).resolve().parents[1] / 'web'


def append_run(store, session='match-20261125', seconds=3):
    path = store / 'alerts' / session / 'positions.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps({'type': 'header', 'team': 'B', 'other': 'A', 'direction': -1, 'pitch_length': 89.0, 'pitch_width': 62.0, 'first_second': 0.0}) + '\n')
        for t in range(seconds):
            handle.write(json.dumps({'type': 'second', 'time': float(t), 'team': [[1, 1.0, 1.0]] * 8, 'other': []}) + '\n')


def times(store):
    path = store / 'service' / 'setup' / 'restart_times.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []


def test_the_default_is_about_ten_seconds(env):
    client, store, procs, _ = env
    assert setup_routes.DEFAULT_RESTART_SECONDS == 10
    assert client.get('/api/v1/setup').json()['restart_seconds'] == 10


def test_a_restart_of_the_red_band_is_measured_once(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={}, headers=H)
    append_run(store)
    client.get('/api/v1/setup')
    assert len(times(store)) == 1                                       # the first start
    procs.running.clear()                                               # the run ends; the earlier seconds stay in the file
    client.post('/api/v1/setup/restart', json={}, headers=H)
    client.get('/api/v1/setup')
    assert len(times(store)) == 1                                       # not yet: only the old run's seconds, after the old header
    append_run(store, seconds=2)                                        # the new run's header and its first seconds
    state = client.get('/api/v1/setup').json()
    client.get('/api/v1/setup')
    assert len(times(store)) == 2 and state['restart_seconds'] == sorted(times(store))[1]
    run = json.loads((store / 'service' / 'setup' / 'run.json').read_text(encoding='utf-8'))
    assert run['measured'] and isinstance(run['first_second_s'], int)


def test_the_words_of_the_page_and_the_band(env):
    banner = (WEB / 'watch-banner.js').read_text(encoding='utf-8')
    setup = (WEB / 'setup.js').read_text(encoding='utf-8')
    assert '분석을 다시 시작했습니다. 10초쯤 뒤에 화면이 돌아옵니다.' in banner and '1분쯤 뒤에' not in banner
    assert '약 2분' not in setup and setup.count('약 1분 30초') == 3
    assert '약 2분' not in Path(setup_routes.__file__).read_text(encoding='utf-8')


def test_the_shown_seconds_are_the_middle_of_the_last_three_measures(env):
    client, store, procs, _ = env
    path = store / 'service' / 'setup' / 'restart_times.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    for written, shown in (([22], 22), ([22, 5, 7], 7), ([40, 22, 5, 7, 9], 7)):
        path.write_text(json.dumps(written), encoding='utf-8')
        assert client.get('/api/v1/setup').json()['restart_seconds'] == shown
    path.unlink()
    assert client.get('/api/v1/setup').json()['restart_seconds'] == 10


def test_the_second_half_question_does_not_say_the_analysis_starts_again():
    banner = (WEB / 'watch-banner.js').read_text(encoding='utf-8')
    assert '후반으로 넘어갑니다.' in banner and '맞습니까?' in banner and '전반 기록은 그대로 보관됩니다.' in banner
    assert '분석이 처음부터 다시 시작됩니다' not in banner
