"""P2 of the second rehearsal (2026-11-25): a restart uses the direction a person confirmed last, not the temporary one of the warm-up run.

Rehearsal: the warm-up run (temporary direction -1) was ended at 01:23:49, "오른쪽으로 공격" was confirmed at 01:26:27 while it was off, and the red band's
"분석 다시 시작" at 01:29:30 started it with -1 again (rehearsal2/store/service/setup/actions.jsonl). Every way of starting again must take
the newest confirmed direction, and after the switch to the second half the second-half direction."""
import json
import time
from pathlib import Path

from app import setup_routes
from tests.test_setup_routes import H, choose_colours, env, new_match, write_candidates  # noqa: F401  (env is a fixture)
from tests.test_setup_warmup import direction_of, write_second

WEB = Path(setup_routes.__file__).resolve().parents[1] / 'web'


def warm_up_then_die_then_confirm(client, store, procs, confirmed=1):
    new_match(client)
    choose_colours(store)
    assert client.post('/api/v1/setup/start', json={}, headers=H).status_code == 200          # warm-up start: temporary direction
    assert direction_of(procs.launched[-1][0]) == setup_routes.TEMPORARY_DIRECTION
    procs.running.clear()                                                                       # the analysis ends while nobody looks
    reply = client.post('/api/v1/setup/kickoff/direction', json={'direction': confirmed}, headers=H)
    assert reply.json() == {'direction': confirmed, 'restarted': False}                         # off: only kept for the next start


def test_the_red_band_restart_takes_the_confirmed_direction(env):
    client, store, procs, _ = env
    warm_up_then_die_then_confirm(client, store, procs, 1)
    assert "fetch('/api/v1/setup/restart'" in (WEB / 'watch-banner.js').read_text(encoding='utf-8')    # the band's button posts here
    assert client.get('/api/v1/setup').json()['analysis']['restart_direction'] == 1
    assert client.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200
    assert direction_of(procs.launched[-1][0]) == 1
    assert client.get('/api/v1/setup').json()['direction'] == {'value': 1, 'confirmed': True, 'running': 1}


def test_the_setup_restart_and_the_start_button_take_the_confirmed_direction(env):
    client, store, procs, _ = env
    warm_up_then_die_then_confirm(client, store, procs, 1)
    assert "post('/api/v1/setup/restart'" in (WEB / 'setup.js').read_text(encoding='utf-8')
    assert client.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200
    assert direction_of(procs.launched[-1][0]) == 1
    client.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H)
    time.sleep(0.01)
    assert client.post('/api/v1/setup/start', json={}, headers=H).status_code == 200            # "분석 미리 시작" without a direction
    assert direction_of(procs.launched[-1][0]) == 1


def test_the_automatic_restart_after_new_colours_takes_the_confirmed_direction(env, monkeypatch):
    client, store, procs, _ = env
    monkeypatch.setattr(setup_routes, 'START_LIMIT', 10)          # four starts within a minute here (start, direction, pictures, automatic restart)
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={}, headers=H)
    write_second(store)
    assert client.post('/api/v1/setup/kickoff/direction', json={'direction': 1}, headers=H).json()['restarted'] is True
    write_second(store, direction=1)
    assert client.get('/api/v1/setup').json()['job']['phase'] == 'done'
    time.sleep(1.1)
    assert client.post('/api/v1/setup/kickoff/recolour', json={}, headers=H).json() == {'started': True}
    procs.running.clear()
    time.sleep(1.1)
    write_candidates(store, (9, 8))
    client.get('/api/v1/setup')
    time.sleep(1.1)
    choose_colours(store)
    assert client.get('/api/v1/setup').json()['job']['phase'] == 'starting'
    assert direction_of(procs.launched[-1][0]) == 1


def second_half(store, direction, session='match-20261125'):
    path = store / 'alerts' / session / 'control.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'seq': 1, 'cmd': 'second_half', 'direction': direction, 'at': time.time()}) + '\n', encoding='utf-8')


def test_after_the_switch_every_restart_takes_the_second_half_direction(env):
    client, store, procs, _ = env
    warm_up_then_die_then_confirm(client, store, procs, 1)
    second_half(store, -1)
    assert client.get('/api/v1/setup').json()['analysis']['restart_direction'] == -1
    assert client.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200          # red band and /setup restart
    assert direction_of(procs.launched[-1][0]) == -1
    client.post('/api/v1/setup/stop', json={'confirm': '1125'}, headers=H)
    assert client.post('/api/v1/setup/start', json={}, headers=H).status_code == 200            # the start button
    assert direction_of(procs.launched[-1][0]) == -1
    saved = json.loads((store / 'service' / 'setup' / 'direction.json').read_text(encoding='utf-8'))
    assert saved['direction'] == 1 and saved['confirmed'] is True                               # the first-half choice is kept as it was


def test_without_a_confirmed_direction_the_last_run_direction_is_kept(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    client.post('/api/v1/setup/start', json={}, headers=H)
    procs.running.clear()
    assert client.post('/api/v1/setup/restart', json={}, headers=H).status_code == 200
    assert direction_of(procs.launched[-1][0]) == setup_routes.TEMPORARY_DIRECTION
    assert client.get('/api/v1/setup').json()['direction']['confirmed'] is False
