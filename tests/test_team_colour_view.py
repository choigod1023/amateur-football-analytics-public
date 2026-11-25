"""The shirt colours of the match for the dots of the bench map, the bench alert picture and the half-time maps (app/team_colour_view.py, 2026-11-25)."""
import json

from fastapi.testclient import TestClient

from app.review_public import create_app
from app.team_colour_view import DEFAULT_OURS, DEFAULT_THEIRS, lab_to_hex, team_colours

ORIGIN = 'http://127.0.0.1:8443'


def lab_point(lightness, a, b):
    return [round(0.6 * lightness, 3), a, b]


def write_profile(store, own, opponent):
    folder = store / 'service'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'team_profile.json').write_text(json.dumps({
        'version': 1, 'created': '2026-11-25T18:50:00',
        'own': {'centre': own, 'scale': 5.0, 'people': 9}, 'opponent': {'centre': opponent, 'scale': 5.0, 'people': 9},
        'others': [], 'separation': 3.0, 'note': '', 'source': {}}), encoding='utf-8')


def test_lab_to_hex_gives_the_known_colours():
    assert lab_to_hex(lab_point(100, 0, 0)) == '#ffffff'
    assert lab_to_hex(lab_point(0, 0, 0)) == '#000000'
    red = lab_to_hex(lab_point(53.2, 80.1, 67.2))                  # sRGB red in Lab
    assert int(red[1:3], 16) > 240 and int(red[3:5], 16) < 20 and int(red[5:7], 16) < 20


def test_no_profile_gives_green_and_light_grey_never_red(tmp_path):
    c = team_colours(tmp_path)
    assert c == {'ours': DEFAULT_OURS, 'theirs': DEFAULT_THEIRS, 'ours_name': '', 'theirs_name': '', 'source': 'default'}
    assert DEFAULT_THEIRS.lower() not in ('#f05454', '#ff0000')


def test_a_damaged_profile_falls_back_to_the_defaults(tmp_path):
    (tmp_path / 'service').mkdir()
    (tmp_path / 'service' / 'team_profile.json').write_text('{not json', encoding='utf-8')
    assert team_colours(tmp_path)['source'] == 'default'


def test_the_profile_colours_and_names(tmp_path):
    write_profile(tmp_path, lab_point(45, 65, 30), lab_point(95, 0, 2))          # red shirts for us, white for them
    c = team_colours(tmp_path)
    assert c['source'] == 'profile' and c['ours_name'].endswith('빨간색') and c['theirs_name'] == '흰색'
    assert int(c['ours'][1:3], 16) > int(c['ours'][3:5], 16) + 80                # red channel well above green
    assert min(int(c['theirs'][i:i + 2], 16) for i in (1, 3, 5)) > 220


def test_the_routes_add_team_colours_and_keep_the_other_items(tmp_path):
    client = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    assert client.get('/api/v1/bench/minimap').json() == {'session': None}       # no match: the answer is as before
    folder = tmp_path / 'alerts' / 's1'
    folder.mkdir(parents=True)
    (folder / 'alerts.jsonl').write_text(json.dumps({'time': 1.0, 'kind': 'heartbeat', 'type': 'heartbeat', 'wall': 1.0}) + '\n', encoding='utf-8')
    write_profile(tmp_path, lab_point(85, -45, 70), lab_point(50, 65, 45))       # light green for us, red for them
    answer = client.get('/api/v1/bench/minimap', params={'session': 's1'}).json()
    assert answer['session'] == 's1' and 'positions' in answer
    assert answer['team_colours']['source'] == 'profile' and answer['team_colours']['ours'].startswith('#')
    rich = client.get('/api/v1/halftime/rich', params={'session': 's1'}).json()
    assert rich['session'] == 's1' and rich['team_colours'] == answer['team_colours']
