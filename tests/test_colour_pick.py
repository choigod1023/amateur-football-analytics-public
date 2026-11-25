"""2026-11-25 colour pick: several colour groups, the own AND the opponent group chosen, automatic retakes of a weak sample."""
import importlib.util
import json
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import colour_pick, setup_routes, team_select_routes  # noqa: E402
from app.small_box_team import reader_decision  # noqa: E402
from app.team_color_profile import ProfileClassifier, load_profile, make_profile, save_profile, split_teams, split_teams_multi  # noqa: E402

GREEN, RED = (24.0, -18.0, 30.0), (21.0, 33.0, 9.0)                 # [0.6 L, a, b] of the 11-20 bibs (the rehearsal centres)
BLACK, GREY = (8.0, 0.0, 1.0), (26.0, 1.0, 2.0)                      # a black coat / referee, a grey jacket
NEON, DARK = (49.0, -20.0, 70.0), (4.0, 0.0, 0.0)


def people(rng, centre, n, spread=2.0):
    return [np.array(centre) + rng.normal(0, spread, 3) for _ in range(n)]


def clear_two(seed=1):
    rng = np.random.default_rng(seed)
    return people(rng, NEON, 60) + people(rng, DARK, 50) + people(rng, (30.0, 60.0, 40.0), 2)


def mixed(seed=2):
    """Green and red bibs with many dark people (referee, coats): the two-group split puts red and dark together."""
    rng = np.random.default_rng(seed)
    return people(rng, GREEN, 120, 3.0) + people(rng, RED, 90, 3.0) + people(rng, BLACK, 110, 3.0) + people(rng, GREY, 70, 3.0)


# ---- A: groups ---------------------------------------------------------------------------------------------------------------
def test_two_clear_colours_give_exactly_the_old_split():
    colours = clear_two()
    old, new = split_teams(colours), split_teams_multi(colours)
    assert new['k'] == 2
    assert {k: v for k, v in new.items() if k not in ('k', 'min_share_people')} == old
    for own in (0, 1):
        assert make_profile(new, own, now='t') == make_profile(old, own, now='t') == make_profile(old, own, now='t', opponent_group=1 - own)


def test_a_dark_crowd_gets_its_own_group_and_the_red_bibs_stay_apart():
    colours = mixed()
    old, new = split_teams(colours), split_teams_multi(colours)
    old_on, _ = reader_decision(make_profile(old, 0))
    assert not old_on                                                   # the rehearsal failure: one group is a red-and-dark mixture
    assert new['k'] >= 3 and new['ok']
    reds = [i for i, g in enumerate(new['groups']) if g['centre'][1] > 20]
    greens = [i for i, g in enumerate(new['groups']) if g['centre'][1] < -10 and g['centre'][2] > 20]
    assert len(reds) == 1 and len(greens) == 1
    profile = make_profile(new, greens[0], opponent_group=reds[0], now='t')
    assert reader_decision(profile)[0]
    assert len(profile['others']) >= len(new['groups']) - 2                # the groups nobody chose are kept as 'others' (not read by the live run)
    assert colour_pick.sample_score(new)['on'] and not colour_pick.sample_score(old)['on']


def test_small_groups_are_no_choice():
    colours = mixed()
    new = split_teams_multi(colours)
    assert all(len(g['members']) >= new['min_share_people'] for g in new['groups'])
    assert new['min_share_people'] == max(4, int(np.ceil(0.05 * len(colours))))


def test_profile_of_a_multi_choice_has_the_old_format(tmp_path):
    new = split_teams_multi(mixed())
    profile = make_profile(new, 0, opponent_group=1, note='n')
    path = tmp_path / 'team_profile.json'
    save_profile(path, profile)
    loaded = load_profile(path)
    assert set(loaded) == {'version', 'created', 'own', 'opponent', 'others', 'separation', 'note', 'source'}
    assert ProfileClassifier(loaded).classify(new['groups'][0]['centre']) == 'own'


def test_make_profile_refuses_unclear_choices():
    new = split_teams_multi(mixed())
    with pytest.raises(ValueError):
        make_profile(new, 0)                                           # three or more groups need the opponent
    with pytest.raises(ValueError):
        make_profile(new, 1, opponent_group=1)
    with pytest.raises(ValueError):
        make_profile(split_teams(clear_two()), 0, opponent_group=0)


# ---- A: the choice API --------------------------------------------------------------------------------------------------------
def write_candidates(store, split, created='2026-11-25T10:00:00'):
    folder = store / 'service' / 'team_select'
    folder.mkdir(parents=True, exist_ok=True)
    groups = [{'id': i, 'people': len(g['members']), 'colour_text': f'색{i}', 'images': []} for i, g in enumerate(split['groups'])]
    record = {'created': created, 'ok': split['ok'], 'weak': split['weak'], 'groups': groups, 'source': 'x.mp4', 'start': 0, 'seconds': 60,
              'split': {'groups': split['groups'], 'others': split['others'], 'separation': split['separation'], 'ok': split['ok'], 'weak': split['weak']}}
    (folder / 'candidates.json').write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    return record


@pytest.fixture
def api(tmp_path):
    app = FastAPI()
    web = tmp_path / 'web'
    web.mkdir()
    team_select_routes.install(app, tmp_path / 'store', web)
    return TestClient(app), tmp_path / 'store'


def test_two_groups_choose_once_as_before(api):
    client, store = api
    record = write_candidates(store, split_teams(clear_two()))
    reply = client.post('/api/v1/team-select/choose', json={'group': 1, 'created': record['created']}).json()
    assert reply['saved'] is False and reply['sentence'] == team_select_routes.sentence(1, '색1') and reply['reader_on'] in (True, False)
    saved = client.post('/api/v1/team-select/choose', json={'group': 1, 'confirmed': True, 'created': record['created']}).json()
    assert saved['saved']
    profile = json.loads((store / 'service' / 'team_profile.json').read_text(encoding='utf-8'))
    expected = make_profile(record['split'], 1, note=team_select_routes.sentence(1, '색1').replace(' 맞습니까?', ''), now=profile['created'],
                            source={'candidates_created': record['created'], 'video': 'x.mp4', 'start': 0, 'seconds': 60})
    assert json.loads(json.dumps(expected)) == profile
    assert client.post('/api/v1/team-select/choose', json={'group': 1, 'opponent': 1}).status_code == 400


def test_many_groups_need_the_opponent_too(api):
    client, store = api
    split = split_teams_multi(mixed())
    record = write_candidates(store, split)
    assert client.post('/api/v1/team-select/choose', json={'group': 0}).status_code == 409
    assert client.post('/api/v1/team-select/choose', json={'group': 0, 'opponent': 0}).status_code == 400
    reds = [i for i, g in enumerate(split['groups']) if g['centre'][1] > 20][0]
    greens = [i for i, g in enumerate(split['groups']) if g['centre'][1] < -10 and g['centre'][2] > 20][0]
    reply = client.post('/api/v1/team-select/choose', json={'group': greens, 'opponent': reds, 'created': record['created']}).json()
    assert reply['reader_on'] is True and reply['reader_text'] == '두 팀 색이 잘 구분됩니다.'
    assert '상대 팀은' in reply['sentence']
    client.post('/api/v1/team-select/choose', json={'group': greens, 'opponent': reds, 'confirmed': True, 'created': record['created']})
    profile = load_profile(store / 'service' / 'team_profile.json')
    assert profile['own']['centre'] == [round(v, 3) for v in split['groups'][greens]['centre']]
    assert profile['opponent']['centre'] == [round(v, 3) for v in split['groups'][reds]['centre']]
    assert team_select_routes.PICTURE.match('g4_2.jpg') and not team_select_routes.PICTURE.match('g5_0.jpg')


# ---- B: retakes --------------------------------------------------------------------------------------------------------------
def test_prepare_command_asks_for_two_groups_and_retakes():
    """2026-11-25 decision: retakes ON, several groups OFF (setup_routes.PREPARE_GROUPS = 2), so the groups are always two and no opponent button shows."""
    command = setup_routes.prepare_command('S', {'python': 'py', 'source': 'src', 'calibrations': 'c.json'})
    assert command[-4:] == ['--groups', '2', '--retakes', '2'] and '--pitch-margin' in command
    assert setup_routes.PREPARE_GROUPS == 2 and setup_routes.PREPARE_RETAKES == 2
    script = (ROOT / 'scripts' / 'team_select_prepare.py').read_text(encoding='utf8')
    assert "many_now = args.groups > 2 and" in script and "if args.groups > 2 and args.groups_when" in script   # with 2, both more-groups paths stay shut
    page = (ROOT / 'web' / 'setup.js').read_text(encoding='utf8')
    assert "const many" in page and "ownPicked && i !== ui.pick" in page                                       # the opponent button needs three or more groups


def test_retake_text_shows_the_try_and_a_time_left():
    assert setup_routes.retake_text(None) is None and setup_routes.retake_text({'attempt': 1, 'of': 3}) is None
    text = setup_routes.retake_text({'attempt': 2, 'of': 3, 'first_seconds': 75, 'attempt_began': 100.0}, now=110.0)
    assert text.startswith('팀 색이 뚜렷하지 않아 한 번 더 찍는 중입니다 (2/3).') and '약 2분 20초' in text
    assert '약 10초' in setup_routes.retake_text({'attempt': 3, 'of': 3, 'first_seconds': 75, 'attempt_began': 0.0}, now=500.0)


def load_prepare(monkeypatch, samples):
    """scripts/team_select_prepare.py with the reader and the detector replaced: each read gives the next list of colours (one person per frame)."""
    spec = importlib.util.spec_from_file_location('team_select_prepare_t', ROOT / 'scripts' / 'team_select_prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import startup_check
    reads = []

    current = {}

    def fake_read(cv2, source, start, seconds, is_file):
        colours = samples[min(len(reads), len(samples) - 1)]
        reads.append(start)
        current.update(i=0, colours=colours)
        return [(float(i), np.zeros((120, 60, 3), np.uint8) + i % 7) for i in range(len(colours))], [], 0, 30.0, (60, 120)

    def fake_detect(detector, frame, camera, device, confidence):
        return [[5.0, 10.0, 45.0, 70.0, 0.9]]

    def fake_colour(frame, box):
        index = current['i']
        current['i'] += 1
        return np.array(current['colours'][index])
    monkeypatch.setattr(startup_check, 'read_source', fake_read)
    monkeypatch.setitem(sys.modules, 'ultralytics', types.SimpleNamespace(YOLO=lambda path: object()))
    monkeypatch.setitem(sys.modules, 'track_review_clip', types.SimpleNamespace(detect=fake_detect))
    import app.team_color_profile as tcp
    monkeypatch.setattr(tcp, 'shirt_colour', fake_colour)
    return module, reads


def run_prepare(module, monkeypatch, store, *extra):
    video = store.parent / 'v.mp4'
    video.write_bytes(b'x')
    monkeypatch.setattr(sys, 'argv', ['p', str(video), '--store', str(store), '--seconds', '60', *extra])
    module.main()
    return json.loads((store / 'service' / 'team_select' / 'candidates.json').read_text(encoding='utf-8'))


def clear_red_green(seed=7):
    rng = np.random.default_rng(seed)
    return people(rng, GREEN, 100, 3.0) + people(rng, RED, 90, 3.0) + people(rng, BLACK, 8, 3.0)


def test_a_clear_first_sample_is_not_taken_again(tmp_path, monkeypatch):
    module, reads = load_prepare(monkeypatch, [clear_red_green(), mixed(3), mixed(4)])
    record = run_prepare(module, monkeypatch, tmp_path / 's', '--groups', '5', '--retakes', '2')
    assert reads == [0.0] and record['attempts'][0]['on'] and record['attempt_used'] == 1 and record['clear'] and len(record['groups']) == 2
    assert not (tmp_path / 's' / 'service' / 'team_select' / 'progress.json').exists()


def test_a_clear_retake_keeps_two_groups(tmp_path, monkeypatch):
    module, reads = load_prepare(monkeypatch, [mixed(), clear_red_green(), mixed(4)])
    record = run_prepare(module, monkeypatch, tmp_path / 's', '--groups', '5', '--retakes', '2')
    assert reads == [0.0, 60.0] and record['attempt_used'] == 2 and record['clear'] and len(record['groups']) == 2


def test_more_groups_first_is_still_possible(tmp_path, monkeypatch):
    module, reads = load_prepare(monkeypatch, [mixed(), mixed(3), mixed(4)])
    record = run_prepare(module, monkeypatch, tmp_path / 's', '--groups', '5', '--retakes', '2', '--groups-when', 'first')
    assert reads == [0.0] and record['clear'] and len(record['groups']) >= 3


def test_more_groups_only_when_every_sample_is_weak(tmp_path, monkeypatch):
    rng = np.random.default_rng(5)
    grey_only = people(rng, GREY, 40, 3.0) + people(rng, BLACK, 40, 3.0)         # no colour at all: never clear
    module, reads = load_prepare(monkeypatch, [grey_only, grey_only, mixed()])
    record = run_prepare(module, monkeypatch, tmp_path / 's', '--groups', '5', '--retakes', '2')
    assert reads == [0.0, 60.0, 120.0] and record['attempt_used'] == 3 and record['clear'] and len(record['attempts']) == 3
    assert len(record['groups']) >= 3 and record['attempts'][2]['more_groups']
    module, reads = load_prepare(monkeypatch, [grey_only, grey_only, grey_only])
    record = run_prepare(module, monkeypatch, tmp_path / 't', '--groups', '5', '--retakes', '2')
    assert len(reads) == 3 and not record['clear'] and record['ok']                # all three weak: the best one is still shown


def test_the_old_command_writes_the_old_file(tmp_path, monkeypatch):
    module, reads = load_prepare(monkeypatch, [clear_two()])
    record = run_prepare(module, monkeypatch, tmp_path / 's')
    assert reads == [0.0] and 'attempts' not in record and len(record['groups']) == 2
    assert set(record) == {'created', 'source', 'start', 'seconds', 'people_read', 'ok', 'weak', 'reason', 'separation', 'groups', 'others_people', 'split'}


def test_setup_state_shows_the_retake(tmp_path, monkeypatch):
    from tests.test_setup_routes import FakeProcs, new_match
    monkeypatch.setenv('FOOTBALL_SETUP_RUN_ROOT', str(tmp_path / 'work'))
    store = tmp_path / 'store'
    (store / 'service').mkdir(parents=True)
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'yolo11n.pt').write_bytes(b'x')
    (repo / 'scripts').mkdir()
    (repo / 'scripts' / 'team_select_prepare.py').write_text('', encoding='utf-8')
    monkeypatch.setattr(setup_routes, 'REPO', repo)
    procs = FakeProcs()
    app = FastAPI()
    setup_routes.install(app, store, tmp_path, processes=procs, frame_source=lambda: b'\xff\xd8x\xff\xd9', memory=lambda: (20.0, 9.0), receiver_check=lambda: True)
    client = TestClient(app)
    new_match(client)
    for _ in range(50):
        if client.get('/api/v1/setup').json()['video']['state'] == 'ok':
            break
        time.sleep(0.05)
    assert client.post('/api/v1/setup/team-photos', json={}).json() == {'started': True}
    colours = client.get('/api/v1/setup').json()['colours']
    assert colours['state'] == 'making' and colours['text'] == '사진을 만드는 중입니다. 약 1분 30초 걸립니다.' and not colours['retake']
    folder = store / 'service' / 'team_select'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'progress.json').write_text(json.dumps({'attempt': 2, 'of': 3, 'first_seconds': 70, 'attempt_began': time.time()}), encoding='utf-8')
    colours = client.get('/api/v1/setup').json()['colours']
    assert colours['retake'] and '(2/3)' in colours['text']
