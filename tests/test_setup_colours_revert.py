"""P4 of the second rehearsal (2026-11-25): "팀 색 다시 찍기" can make the own count worse (7-11 -> 2-3 own players: the second picture read the opponent as achromatic,
'Small-box team reader OFF: opponent colour chroma 11.3 < 17.97'). The colours before are kept and come back with one press, the page warns when the new colours
read fewer own players, and the colour pictures say beforehand whether the run will switch the bib-colour reader off."""
import json
import time

import pytest

from app import setup_routes, small_box_team
from app.setup_routes import REVERT_LABEL, WEAK_PICTURES_TEXT, reader_preview, recolour_worse
from app.team_color_profile import make_profile
from tests.test_setup_routes import H, choose_colours, env, new_match  # noqa: F401  (env is a fixture)
from tests.test_setup_warmup import direction_of

SESSION = 'match-20261125'
GREEN, RED, GREY = [45.0, -40.0, 35.0], [35.0, 45.0, 25.0], [40.0, 6.0, 9.58]      # [0.6 L, a, b]: chromas 53.2, 51.5, 11.3


def split(own, other):
    return {'ok': True, 'groups': [{'centre': own, 'scale': 5.0, 'members': list(range(9))}, {'centre': other, 'scale': 5.0, 'members': list(range(8))}],
            'others': [], 'separation': 3.0, 'weak': False}


def pictures(store, own=GREEN, other=RED):
    folder = store / 'service' / 'team_select'
    folder.mkdir(parents=True, exist_ok=True)
    groups = [{'colour_text': '연두', 'people': 9, 'images': ['g0_0.jpg']}, {'colour_text': '빨강', 'people': 8, 'images': ['g1_0.jpg']}]
    (folder / 'candidates.json').write_text(json.dumps({'created': time.strftime('%Y-%m-%dT%H:%M:%S'), 'ok': True, 'weak': False, 'groups': groups,
                                                        'split': split(own, other)}), encoding='utf-8')


def seconds(store, own_per_second, count=70, direction=-1):
    path = store / 'alerts' / SESSION / 'positions.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{'type': 'header', 'team': 'B', 'other': 'A', 'direction': direction, 'pitch_length': 89.0, 'pitch_width': 62.0, 'first_second': 0.0}]
    rows += [{'type': 'second', 'time': float(t), 'team': [[i, 1.0, 1.0] for i in range(own_per_second)], 'other': []} for t in range(count)]
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')


def profile_with(store, own, other, note):
    profile = make_profile(split(own, other), 0, note=note)
    (store / 'service' / 'team_profile.json').write_text(json.dumps(profile, ensure_ascii=False), encoding='utf-8')
    return profile


def recolour_and_choose(client, store, procs, before, after, new_colours=(GREEN, GREY)):
    """Warm-up run with good colours (`before` own players a second), "팀 색 다시 찍기", new pictures, the own team chosen again, the new run reads `after`."""
    new_match(client)
    first = profile_with(store, GREEN, RED, '우리 팀은 첫째 묶음 연두 옷 팀입니다.')
    assert client.post('/api/v1/setup/start', json={}, headers=H).status_code == 200
    seconds(store, before)
    assert client.get('/api/v1/setup').json()['check']['own_mean'] == before
    time.sleep(1.1)
    assert client.post('/api/v1/setup/kickoff/recolour', json={}, headers=H).json() == {'started': True}
    procs.running.clear()                                                                   # the pictures are made
    time.sleep(1.1)
    pictures(store, *new_colours)
    assert client.get('/api/v1/setup').json()['job']['phase'] == 'choose'
    time.sleep(1.1)
    profile_with(store, *new_colours, '우리 팀은 첫째 묶음 연두 옷 팀입니다.')            # the own team chosen on the new pictures
    assert client.get('/api/v1/setup').json()['job']['phase'] == 'starting'
    seconds(store, after)
    return first


def a_minute_later(store):
    path = store / 'service' / 'setup' / 'colours_previous.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value['restarted_at'] -= setup_routes.RECOLOUR_LOOK_AFTER + 1
    path.write_text(json.dumps(value), encoding='utf-8')
    run_path = store / 'service' / 'setup' / 'run.json'
    run = json.loads(run_path.read_text(encoding='utf-8'))
    run['started_at'] -= setup_routes.RECOLOUR_LOOK_AFTER + 1
    run_path.write_text(json.dumps(run), encoding='utf-8')


@pytest.mark.parametrize('before, after, warned', [(8, 3, True), (8, 7, False), (4, 5, False), (7, 5, True), (9, 6, True)])
def test_the_warning_shows_only_under_its_condition(env, before, after, warned):
    client, store, procs, _ = env
    recolour_and_choose(client, store, procs, before, after)
    previous = client.get('/api/v1/setup').json()['colours_previous']
    assert previous['available'] is True and previous['before_mean'] == before
    assert previous['judged'] is False and previous['worse'] is False                    # not before the new analysis has run a minute
    a_minute_later(store)
    previous = client.get('/api/v1/setup').json()['colours_previous']
    assert previous['judged'] is True and previous['worse'] is warned
    if warned:
        assert previous['text'] == f"다시 찍은 팀 색으로 우리 팀이 {after}명만 잡힙니다. '이전 팀 색으로 되돌리기'를 누르세요."
    else:
        assert previous['text'] is None


def test_the_rule_of_the_warning():
    assert recolour_worse(8, 3) is True and recolour_worse(8, 7) is False and recolour_worse(4, 5) is False
    assert recolour_worse(7, 5) is True and recolour_worse(3, 3) is False and recolour_worse(None, 4) is True
    assert recolour_worse(9, 6) is True and recolour_worse(9, 6.5) is False and recolour_worse(None, 7) is False and recolour_worse(8, None) is False


def test_revert_brings_the_old_colours_back_and_starts_the_analysis_again(env, monkeypatch):
    client, store, procs, _ = env
    monkeypatch.setattr(setup_routes, 'START_LIMIT', 10)          # start, pictures, automatic restart and the revert within a minute here
    first = recolour_and_choose(client, store, procs, 8, 3)
    archived = list((store / 'service' / '_archive').glob('*-before-recolour-match-20261125/team_profile.json'))
    assert len(archived) == 1 and json.loads(archived[0].read_text(encoding='utf-8'))['own']['centre'] == first['own']['centre']
    assert client.get('/api/v1/setup').json()['job']['phase'] == 'done'                  # the new analysis wrote its first second
    launched = len(procs.launched)
    reply = client.post('/api/v1/setup/kickoff/colours-revert', json={}, headers=H)
    assert reply.status_code == 200, reply.text
    assert len(procs.launched) == launched + 1 and 'run_live_feedback.py' in procs.launched[-1][0][1]      # the restart command went out
    assert len([kind for kind in procs.running.values() if kind == 'run']) == 1                             # the run with the new colours was ended
    assert direction_of(procs.launched[-1][0]) == -1
    profile = json.loads((store / 'service' / 'team_profile.json').read_text(encoding='utf-8'))
    assert profile['own']['centre'] == first['own']['centre'] and profile['opponent']['centre'] == first['opponent']['centre']
    assert profile['restored_created'] == first['created']
    state = client.get('/api/v1/setup').json()
    assert state['job']['kind'] == 'revert' and state['job']['phase'] == 'starting' and state['colours']['state'] == 'ok'
    assert state['colours_previous']['available'] is False and state['colours_previous']['worse'] is False
    assert client.post('/api/v1/setup/kickoff/colours-revert', json={}, headers=H).status_code == 409       # once
    log = [json.loads(line) for line in (store / 'service' / 'setup' / 'actions.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [r['action'] for r in log if r['result'] == 'ok'][-1] == 'colours_revert'


def test_a_refused_revert_leaves_the_analysis_and_the_colours_as_they_are(env):
    client, store, procs, _ = env
    recolour_and_choose(client, store, procs, 8, 3)                  # three starts within the minute: a fourth is refused
    assert client.get('/api/v1/setup').json()['job']['phase'] == 'done'
    before = (store / 'service' / 'team_profile.json').read_text(encoding='utf-8')
    running = dict(procs.running)
    reply = client.post('/api/v1/setup/kickoff/colours-revert', json={}, headers=H)
    assert reply.status_code == 429
    assert procs.running == running and (store / 'service' / 'team_profile.json').read_text(encoding='utf-8') == before
    assert client.get('/api/v1/setup').json()['colours_previous']['available'] is True


def test_revert_is_refused_without_an_earlier_choice(env):
    client, store, procs, _ = env
    new_match(client)
    choose_colours(store)
    assert client.post('/api/v1/setup/kickoff/colours-revert', json={}, headers=H).status_code == 409
    assert client.get('/api/v1/setup').json()['colours_previous'] is None


def test_the_pictures_tell_beforehand_when_the_reader_will_be_off(env):
    client, store, procs, _ = env
    new_match(client)
    pictures(store, GREEN, RED)
    colours = client.get('/api/v1/setup').json()['colours']
    assert colours['reader_on'] is True and 'reader_text' not in colours
    pictures(store, GREEN, GREY)
    colours = client.get('/api/v1/setup').json()['colours']
    assert colours['reader_on'] is False and colours['reader_line'].startswith('Small-box team reader OFF: opponent colour chroma 11.3 < 17.97')
    assert colours['reader_text'] == '이 사진으로는 두 팀 색 구분이 약합니다. 다시 찍으세요.'          # no earlier colours to go back to yet


def test_after_recolour_the_weak_pictures_text_names_the_earlier_colours(env):
    client, store, procs, _ = env
    new_match(client)
    profile_with(store, GREEN, RED, 'x')
    client.post('/api/v1/setup/start', json={}, headers=H)
    seconds(store, 8)
    time.sleep(1.1)
    client.post('/api/v1/setup/kickoff/recolour', json={}, headers=H)
    procs.running.clear()
    time.sleep(1.1)
    pictures(store, GREEN, GREY)
    colours = client.get('/api/v1/setup').json()['colours']
    assert colours['reader_on'] is False and colours['reader_text'] == WEAK_PICTURES_TEXT
    assert client.get('/api/v1/setup').json()['colours_previous']['label'] == REVERT_LABEL


def test_weak_pictures_can_be_taken_again_before_the_choice(env, monkeypatch):
    client, store, procs, _ = env
    monkeypatch.setattr(setup_routes, 'START_LIMIT', 10)
    new_match(client)
    first = profile_with(store, GREEN, RED, 'x')
    client.post('/api/v1/setup/start', json={}, headers=H)
    seconds(store, 8)
    time.sleep(1.1)
    client.post('/api/v1/setup/kickoff/recolour', json={}, headers=H)
    procs.running.clear()
    time.sleep(1.1)
    pictures(store, GREEN, GREY)
    assert client.get('/api/v1/setup').json()['job']['phase'] == 'choose'
    assert client.post('/api/v1/setup/kickoff/recolour', json={}, headers=H).json() == {'started': True}     # "다시 찍거나"
    assert list(procs.running.values()) == ['prepare']
    kept = json.loads((store / 'service' / 'setup' / 'colours_previous.json').read_text(encoding='utf-8'))
    assert kept['profile_created'] == first['created'] and kept['before_mean'] == 8                       # still the colours before the first new pictures


def test_the_preview_uses_the_run_s_own_rule(monkeypatch):
    candidates = {'split': split(GREEN, GREY)}
    assert reader_preview(candidates) == small_box_team.reader_decision(make_profile(split(GREEN, GREY), 0))
    assert reader_preview(candidates)[0] is small_box_team.reader_decision(make_profile(split(GREEN, GREY), 1))[0] is False   # the choice of group does not change ON/OFF
    monkeypatch.setattr(small_box_team, 'reader_decision', lambda profile: ('same function', 'x'))
    assert reader_preview(candidates) == ('same function', 'x')
    assert reader_preview({}) is None
