import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.team_color_profile import (ProfileClassifier, colour_name, load_profile, make_profile, profile_fit, save_profile, shirt_colour, split_teams)  # noqa: E402


def frame_with_shirt(bgr, size=(200, 100)):
    image = np.full((size[0], size[1], 3), (40, 120, 40), np.uint8)       # grass
    image[:, 20:80] = bgr
    return image


def people(rng, centre, n, spread=2.0):
    return [np.array(centre) + rng.normal(0, spread, 3) for _ in range(n)]


BLACK, NEON = (4.0, 0.0, 0.0), (82.0 * 0.6, -20.0, 70.0)         # [0.6 L, a, b] of a dark team and a neon team
BLUE = (50 * 0.6, 20.0, -55.0)


def test_shirt_colour_tells_colours_apart_and_skips_small_boxes():
    dark = shirt_colour(frame_with_shirt((25, 25, 25)), [20, 0, 80, 100])
    neon = shirt_colour(frame_with_shirt((40, 240, 220)), [20, 0, 80, 100])
    blue = shirt_colour(frame_with_shirt((200, 60, 20)), [20, 0, 80, 100])
    assert dark[0] < neon[0] and neon[2] > 40 and blue[2] < -20
    assert shirt_colour(frame_with_shirt((25, 25, 25)), [20, 0, 80, 20]) is None         # 20 px tall: too small


def test_split_teams_finds_two_groups_and_puts_the_referee_aside():
    rng = np.random.default_rng(1)
    colours = people(rng, BLACK, 10) + people(rng, NEON, 9) + [np.array((30.0, 0.0, 0.0))]       # a grey referee
    split = split_teams(colours)
    assert split['ok'] and not split['weak']
    sizes = sorted(len(g['members']) for g in split['groups'])
    assert sizes == [9, 10]
    assert [m for g in split['others'] for m in g['members']] == [19]


def test_split_teams_refuses_too_few_and_warns_about_close_colours():
    rng = np.random.default_rng(2)
    assert split_teams(people(rng, BLACK, 5))['ok'] is False
    close = split_teams(people(rng, (10.0, 0.0, 0.0), 10, 3.0) + people(rng, (14.0, 1.0, 0.0), 10, 3.0))
    assert close['ok'] and close['weak'] and '비슷' in close['reason']


def test_profile_roundtrip_and_choice_decides_who_is_own(tmp_path):
    rng = np.random.default_rng(3)
    colours = people(rng, BLACK, 10) + people(rng, NEON, 9)
    split = split_teams(colours)
    path = tmp_path / 'service' / 'team_profile.json'
    assert load_profile(path) is None
    own_black = 0 if np.linalg.norm(np.array(split['groups'][0]['centre']) - np.array(BLACK)) < 10 else 1
    save_profile(path, make_profile(split, own_black, note='x'))
    classifier = ProfileClassifier(load_profile(path))
    assert classifier.classify(np.array(BLACK) + 1) == 'own' and classifier.classify(np.array(NEON) + 1) == 'opponent'
    save_profile(path, make_profile(split, 1 - own_black))                   # the coach picks the other side: the labels swap
    swapped = ProfileClassifier(load_profile(path))
    assert swapped.classify(np.array(BLACK)) == 'opponent' and swapped.classify(np.array(NEON)) == 'own'
    assert not list(path.parent.glob('*.tmp'))


def test_damaged_profile_is_an_error_not_a_silent_fallback(tmp_path):
    path = tmp_path / 'team_profile.json'
    path.write_text('{"version": 1, "own": {"centre": [1]}}', encoding='utf-8')
    with pytest.raises(ValueError):
        load_profile(path)
    path.write_text('not json', encoding='utf-8')
    with pytest.raises(ValueError):
        load_profile(path)


def test_classifier_leaves_far_and_in_between_colours_unclear():
    rng = np.random.default_rng(4)
    split = split_teams(people(rng, BLACK, 10) + people(rng, BLUE, 10))
    classifier = ProfileClassifier(make_profile(split, 0))
    assert classifier.classify(None) is None
    assert classifier.classify(np.array(NEON)) is None                       # a third colour (goalkeeper, referee) is not forced into a team
    middle = (np.array(BLACK) + np.array(BLUE)) / 2
    assert classifier.classify(middle) is None


def test_profile_fit_warns_when_the_clothes_changed():
    rng = np.random.default_rng(5)
    split = split_teams(people(rng, BLACK, 10) + people(rng, NEON, 9))
    profile = make_profile(split, 0)
    assert profile_fit(profile, people(rng, BLACK, 6) + people(rng, NEON, 6))['ok']
    changed = profile_fit(profile, people(rng, (60.0, 30.0, -40.0), 8) + people(rng, NEON, 6))
    assert not changed['ok'] and changed['own'] + changed['opponent'] < changed['people']
    assert not profile_fit(profile, [])['ok']


def test_colour_names_are_plain_words():
    assert colour_name(BLACK) == '검은색'
    assert colour_name(NEON) == '형광 노란색'
    assert colour_name(BLUE) == '파란색'


def test_team_vote_follows_the_profile(tmp_path):
    pytest.importorskip('ultralytics')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from run_live_feedback import TeamVotes
    rng = np.random.default_rng(6)
    dark_frame, neon_frame = frame_with_shirt((10, 10, 10)), frame_with_shirt((40, 240, 220))
    dark_colour, neon_colour = shirt_colour(dark_frame, [20, 0, 80, 100]), shirt_colour(neon_frame, [20, 0, 80, 100])
    split = split_teams(people(rng, dark_colour, 10) + people(rng, neon_colour, 9))
    black_group = 0 if np.linalg.norm(np.array(split['groups'][0]['centre']) - dark_colour) < 10 else 1
    # the own team wears the BRIGHT colour here: the coach chose the neon group; the fixed old rule would call it team A
    votes = TeamVotes(profile=make_profile(split, 1 - black_group), own_letter='B', other_letter='A')
    for _ in range(3):
        votes.observe(1, neon_frame, [20, 0, 80, 100])
        votes.observe(2, dark_frame, [20, 0, 80, 100])
    assert votes.label(1) == 'B' and votes.label(2) == 'A'
    old = TeamVotes()
    for _ in range(3):
        old.observe(1, neon_frame, [20, 0, 80, 100])
    assert old.label(1) == 'A'                                               # without a profile nothing changes


def test_routes_choose_with_confirmation_and_write_profile(tmp_path):
    pytest.importorskip('fastapi.testclient')
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.team_select_routes import install
    rng = np.random.default_rng(7)
    split = split_teams(people(rng, BLACK, 10) + people(rng, NEON, 9))
    folder = tmp_path / 'service' / 'team_select'
    folder.mkdir(parents=True)
    (folder / 'g0_0.jpg').write_bytes(b'\xff\xd8\xff\xd9')
    groups = [{'id': i, 'people': len(g['members']), 'colour_text': colour_name(g['centre']), 'images': ['g0_0.jpg']} for i, g in enumerate(split['groups'])]
    record = {'created': '2026-11-18T10:00:00', 'source': 'a.mp4', 'start': 64, 'seconds': 10, 'people_read': 19, 'ok': True, 'weak': False, 'reason': '', 'separation': split['separation'],
              'groups': groups, 'others_people': 0, 'split': split}
    (folder / 'candidates.json').write_text(json.dumps(record), encoding='utf-8')
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'team_select.html').write_text('<html></html>', encoding='utf-8')
    (web / 'team_select.js').write_text('//', encoding='utf-8')
    app = FastAPI()
    install(app, tmp_path, web)
    client = TestClient(app)
    state = client.get('/api/v1/team-select').json()
    assert state['profile'] is None and state['candidates']['groups'][0]['urls'] == ['/team-select-files/g0_0.jpg'] and 'split' not in state['candidates']
    assert client.get('/team-select').status_code == 200 and client.get('/team-select-files/g0_0.jpg').status_code == 200
    assert client.get('/team-select-files/../candidates.json').status_code in (404, 422)
    ask = client.post('/api/v1/team-select/choose', json={'group': 0, 'created': record['created']}).json()
    assert ask['saved'] is False and ask['sentence'].startswith('우리 팀은 사진 왼쪽') and 'unconfirmed' not in ask
    assert not (tmp_path / 'service' / 'team_profile.json').exists()                  # asking does not save
    assert client.post('/api/v1/team-select/choose', json={'group': 0, 'confirmed': True, 'created': 'old'}).status_code == 409
    done = client.post('/api/v1/team-select/choose', json={'group': 1, 'confirmed': True, 'created': record['created']}).json()
    assert done['saved'] and done['sentence'].startswith('우리 팀은 사진 오른쪽')
    profile = load_profile(tmp_path / 'service' / 'team_profile.json')
    assert profile['own']['people'] == groups[1]['people']
    assert client.post('/api/v1/team-select/choose', json={'group': 5, 'confirmed': True}).status_code == 400
    assert client.post('/api/v1/team-select/clear').json() == {'cleared': True}
    assert load_profile(tmp_path / 'service' / 'team_profile.json') is None
