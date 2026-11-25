"""The picture-first half-time report (app/halftime_rich.py): the kick-off window, the rules of the second-half suggestions, the places of the line-up, and the
pages that must not break on missing data. Names in these tests are made up."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from app import halftime_rich as hr
from app.review_public import create_app

ROOT_DIR = Path(__file__).resolve().parents[1]
WALL = 1_800_000_000.0          # clock time of analysis second 0 in these runs (heartbeat wall - time)


def team_points(back_u, n=10, spread=8.0, keeper=True):
    """Our points in the team's frame for a 4-3-3 like spread: a keeper near the own goal line and n outfield players from back_u forward (u = x * d)."""
    pts = [(-42.0, 0.0)] if keeper else []
    rows = [back_u, back_u + spread, back_u + 2 * spread]
    per = [4, 3, 3] if n == 10 else [max(1, n // 3)] * 3
    for line, count in zip(rows, per):
        for k in range(count):
            pts.append((line, -15.0 + 30.0 * k / max(1, count - 1)))
    return pts[:n + (1 if keeper else 0)]


def write_run(store, session='m1', seconds=range(0, 600), direction=-1, ours=None, theirs=None, kickoff=None, alerts=(), end_tag=None, lineup=None, score=()):
    """A run in the store: positions (screen metres: x = u * d), heartbeats every 5 s, tags (kick-off etc.) and alert rows."""
    folder = store / 'alerts' / session
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / 'positions.jsonl', 'w', encoding='utf-8') as out:
        out.write(json.dumps({'type': 'header', 'team': 'B', 'other': 'A', 'direction': direction, 'pitch_length': 89.0, 'pitch_width': 62.0, 'first_second': 0.0}) + '\n')
        for t in seconds:
            us = ours(t) if ours else team_points(-25.0)
            them = theirs(t) if theirs else [(-u, -v) for u, v in team_points(-25.0)]   # their own frame mirrored into ours
            out.write(json.dumps({'type': 'second', 'time': float(t), 'team': [[i, u * direction, v * direction] for i, (u, v) in enumerate(us)],
                                  'other': [[100 + i, u * direction, v * direction] for i, (u, v) in enumerate(them)]}) + '\n')
    with open(folder / 'alerts.jsonl', 'w', encoding='utf-8') as out:
        for t in range(0, max(seconds) + 1 if seconds else 1, 5):
            out.write(json.dumps({'time': float(t), 'kind': 'heartbeat', 'type': 'heartbeat', 'polarity': 'status', 'wall': WALL + t}) + '\n')
        for t, kind in alerts:
            out.write(json.dumps({'time': float(t), 'kind': kind, 'polarity': 'poor', 'title': kind}) + '\n')
    tags = []
    if kickoff is not None:
        tags.append({'op': 'add', 'id': 'k1', 'kind': 'start_h1', 'epoch': WALL + kickoff})
    if end_tag is not None:
        tags.append({'op': 'add', 'id': 'e1', 'kind': 'end_h1', 'epoch': WALL + end_tag})
    (store / 'analyst-tags').mkdir(exist_ok=True)
    (store / 'analyst-tags' / 'tags.jsonl').write_text(''.join(json.dumps(t) + '\n' for t in tags), encoding='utf-8')
    if score:
        (folder / 'score.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in score), encoding='utf-8')
    if lineup:
        (store / 'service' / 'lineup').mkdir(parents=True, exist_ok=True)
        (store / 'service' / 'lineup' / f'{session}.json').write_text(json.dumps(lineup, ensure_ascii=False), encoding='utf-8')
    return folder


# ---- the kick-off window ------------------------------------------------------------------------------------------------------------------
def test_nothing_before_the_kick_off_mark_counts(tmp_path):
    """Warm-up: 5 alerts and a very low back line before the "전반 시작" mark; none of it may reach the counts or the means."""
    def ours(t):
        return team_points(-40.0 if t < 200 else -25.0)          # the warm-up stands deep; after the kick-off the back line is 19.5 m from the goal line
    warm = [(t, 'conceded_run') for t in (20, 60, 100, 140, 180)]
    write_run(tmp_path, seconds=range(0, 800), ours=ours, kickoff=200, alerts=warm + [(300, 'line_drop'), (500, 'line_drop')],
              score=[{'kind': 'goal', 'team': 'opp', 'analysis': {'positions_time': 150.0}}, {'kind': 'goal', 'team': 'ours', 'analysis': {'positions_time': 400.0}}])
    r = hr.build(tmp_path, 'm1')
    assert r['start_s'] == 200.0
    kinds = {k['kind']: k['count'] for k in r['blocks']['alerts']['kinds']}
    assert kinds == {'line_drop': 2}
    assert sum(k['count'] for k in r['blocks']['alerts']['kinds']) == 2
    for st in r['blocks']['thirds']['stretches']:
        assert abs(st['means']['def'] - 19.5) < 0.01                 # the deep warm-up never enters a mean
    assert all(p['def'] == 19.5 for p in r['blocks']['line']['points'])
    assert r['blocks']['glance']['score'] == {'ours': 1, 'opp': 0}  # the warm-up "goal" is left out
    assert r['blocks']['opponent']['summary']['seen_text']          # the other team's block is made from the same seconds
    assert r['blocks']['glance']['stretches'][0]['from_text'] == '0분'


def test_without_the_kick_off_mark_only_one_line(tmp_path):
    write_run(tmp_path, seconds=range(0, 300), alerts=[(50, 'conceded_run')])
    r = hr.build(tmp_path, 'm1')
    assert r['state'] == 'not_started'
    assert r['status_text'] == '전반 시작을 누르면 집계가 시작됩니다'
    assert r['blocks'] == {}


def test_the_end_is_the_button_then_the_switch_then_the_end_mark(tmp_path):
    write_run(tmp_path, seconds=range(0, 900), kickoff=100, end_tag=700)
    assert hr.build(tmp_path, 'm1')['end_s'] == 700.0
    assert hr.build(tmp_path, 'm1', end_s=650.0, final=True)['end_s'] == 650.0
    r = hr.build(tmp_path, 'm1', end_s=50.0)                           # an end before the kick-off is not an end
    assert r['end_s'] == 700.0


def test_running_half_says_so_far(tmp_path):
    write_run(tmp_path, seconds=range(0, 820), kickoff=100)
    r = hr.build(tmp_path, 'm1')
    assert r['state'] == 'running'
    assert r['status_text'] == '전반 진행 중, 11분 59초까지'


# ---- missing data -----------------------------------------------------------------------------------------------------------------------
def test_no_records_at_all(tmp_path):
    r = hr.build(tmp_path, 'nothing')
    assert r['state'] == 'empty'
    assert all(b['text'] == '기록에 없음' for b in r['blocks'].values())


def test_our_team_hardly_seen(tmp_path):
    write_run(tmp_path, seconds=range(0, 600), kickoff=0, ours=lambda t: team_points(-25.0, n=5, keeper=False) if t % 10 else team_points(-25.0))
    r = hr.build(tmp_path, 'm1')
    for key in ('thirds', 'line', 'sides', 'next'):
        assert r['blocks'][key]['judged'] is False
        assert r['blocks'][key]['text'] == hr.NO_DATA
    assert r['blocks']['next']['items'] == []


def test_the_other_team_not_seen(tmp_path):
    write_run(tmp_path, seconds=range(0, 600), kickoff=0, theirs=lambda t: [(10.0, 0.0), (12.0, 5.0)])
    r = hr.build(tmp_path, 'm1')
    assert r['blocks']['opponent']['judged'] is False
    assert r['blocks']['opponent']['text'] == hr.NOT_JUDGED
    assert r['blocks']['sides']['theirs'] is None
    assert r['blocks']['thirds']['judged'] is True


# ---- the suggestions: each rule fires above its threshold and stays silent under it ---------------------------------------------------------------
BASE = {'usable_ok': True, 'def_first': 30.0, 'def_last': 30.0, 'gap_dm': 10.0, 'gap_ma': 10.0, 'left': 30.0, 'right': 30.0, 'opp_left': 30.0, 'opp_right': 30.0, 'length': 30.0}


def keys(m):
    return [s['key'] for s in hr.suggestions({**BASE, **m}, 89.0, 62.0)]


def test_no_problem_no_suggestion():
    assert keys({}) == []
    assert keys({'usable_ok': False, 'def_last': 10.0}) == []


def test_rule_back_line_dropped():
    assert keys({'def_last': 30.0 - hr.DROP_MIN}) == ['raise_line']
    assert keys({'def_last': 30.0 - hr.DROP_MIN + 0.1}) == []


def test_rule_gaps_between_lines():
    assert keys({'gap_dm': hr.GAP_MAX}) == ['close_dm']
    assert keys({'gap_dm': hr.GAP_MAX - 0.1}) == []
    assert keys({'gap_ma': hr.GAP_MAX + 2}) == ['close_ma']
    assert keys({'gap_ma': hr.GAP_MAX - 0.1}) == []


def test_rule_one_side_beyond_the_other_team():
    assert keys({'left': 45.0, 'right': 30.0}) == ['use_side']                       # 15 points more than the other team's 0
    assert keys({'left': 44.9, 'right': 30.0}) == []
    assert keys({'left': 45.0, 'right': 15.0, 'opp_left': 40.0, 'opp_right': 15.0}) == []   # both teams lean the same way: the camera side, no suggestion
    assert keys({'left': 45.0, 'right': 30.0, 'opp_left': None}) == []


def test_rule_team_too_long():
    assert keys({'length': 44.5}) == ['shorter']
    assert keys({'length': 44.4}) == []


def test_at_most_three_in_order_of_the_excess():
    out = hr.suggestions({**BASE, 'def_last': 10.0, 'gap_dm': 19.0, 'gap_ma': 30.0, 'left': 70.0, 'right': 10.0, 'length': 60.0}, 89.0, 62.0)
    assert [s['key'] for s in out] == ['raise_line', 'use_side', 'close_ma']
    assert all(len(s['text']) <= 40 for s in out)


# ---- the places of the line-up ---------------------------------------------------------------------------------------------------------
LINEUP = {'formation': '4-2-3-1', 'players': [{'role': r, 'name': f'선수{i}'} for i, r in enumerate(
    ['GK', 'LB', 'LCB', 'RCB', 'RB', 'LDM', 'RDM', 'LW', 'AM', 'RW', 'ST'])]}
SHAPE_4231 = [(-42.0, 0.0), (-25, -20), (-26, -7), (-26, 7), (-25, 20), (-12, -8), (-12, 8), (2, -18), (3, 0), (2, 18), (16, 0)]   # keeper + 4-2-3-1, our left is v < 0


def test_line_up_places_from_the_one_table():
    p = hr.places(LINEUP)
    assert p['field'] == 10 and p['unknown'] == []
    assert [[x['role'] for x in g] for g in p['groups']] == hr.FORMATIONS['4-2-3-1']
    assert p['groups'][0][0] == {'role': 'LB', 'name': '선수1'}
    p442 = hr.places({**LINEUP, 'formation': '4-4-2'})                                # codes of another shape: those places keep the code without a name
    assert [x['name'] for x in p442['groups'][1]] == ['', '', '', ''] and 'LDM' in p442['unknown']
    assert hr.places({'formation': '4-2-2-1-1', 'players': [{'role': 'LB', 'name': 'a'}]}) is None   # a shape not in the table: no codes, no names


def test_every_formation_in_the_table_has_ten_distinct_codes():
    for name, rows in hr.FORMATIONS.items():
        codes = [c for row in rows for c in row]
        assert len(codes) == 10 == len(set(codes)), name
        assert [len(r) for r in rows] == [int(x) for x in name.split('-')], name
        for row in rows:                                                              # left to right: an L code never stands right of an R code
            ranks = [0 if c[0] == 'L' else 2 if c[0] == 'R' else 1 for c in row]
            assert ranks == sorted(ranks), (name, row)


def test_assign_places_depth_then_left_to_right():
    pts = [(-30, 10), (-30, -10), (-31, 20), (-29, -20), (-15, 5), (-16, -5), (0, 0), (1, -20), (2, 20), (15, 0)]
    out = hr.assign_places(pts, [4, 2, 3, 1])
    assert out == [(0, 2), (0, 1), (0, 3), (0, 0), (1, 1), (1, 0), (2, 1), (2, 0), (2, 2), (3, 0)]
    assert hr.assign_places(pts[:9], [4, 2, 3, 1]) is None


def test_names_only_when_the_dots_match_the_line_up(tmp_path):
    write_run(tmp_path, seconds=range(0, 600), kickoff=0, lineup=LINEUP, ours=lambda t: SHAPE_4231)
    r = hr.build(tmp_path, 'm1')
    dots = r['blocks']['thirds']['stretches'][0]['dots']
    assert sorted(d['name'] for d in dots) == sorted(f'선수{i}' for i in range(1, 11))
    left_back = next(d for d in dots if d['role'] == 'LB')
    assert left_back['name'] == '선수1' and left_back['v'] < 0 and left_back['line'] == 0
    assert r['blocks']['thirds']['names'] is True
    # one player too many in every second: no second with exactly ten, so no places at all
    write_run(tmp_path, session='m2', seconds=range(0, 600), kickoff=0, lineup=LINEUP, ours=lambda t: SHAPE_4231 + [(-12, 0)])
    r2 = hr.build(tmp_path, 'm2')
    assert all(not d['name'] for s in r2['blocks']['thirds']['stretches'] for d in (s['dots'] or []))


def test_codes_without_a_line_up_come_from_the_dots_or_not_at_all(tmp_path):
    write_run(tmp_path, seconds=range(0, 600), kickoff=0, ours=lambda t: SHAPE_4231)
    r = hr.build(tmp_path, 'm1')
    dots = r['blocks']['thirds']['stretches'][0]['dots']
    assert {d['role'] for d in dots} == {c for row in hr.FORMATIONS['4-2-3-1'] for c in row} and not any(d['name'] for d in dots)
    assert r['blocks']['thirds']['roles'] is True and r['blocks']['thirds']['names'] is False
    assert next(d for d in dots if d['role'] == 'LB')['v'] < 0 and next(d for d in dots if d['role'] == 'RB')['v'] > 0
    # depths that make no shape of the table (five lines of two): dots only
    flat = [(-42.0, 0.0)] + [(u, v) for u in (-30, -20, -10, 0, 10) for v in (-10, 10)]
    assert hr.shape_of(flat[1:]) is None
    write_run(tmp_path, session='m3', seconds=range(0, 600), kickoff=0, ours=lambda t: flat)
    assert not any(d['role'] for s in hr.build(tmp_path, 'm3')['blocks']['thirds']['stretches'] for d in (s['dots'] or []))


def test_left_back_stays_left_in_the_second_half_picture(tmp_path):
    """Block 7 draws the same places (same codes, same team-frame coordinates) and only turns the picture: the left back of the first half is the left back there too."""
    def ours(t):
        return [(u - 12 * t / 600, v) for u, v in SHAPE_4231]                     # the team sinks slowly (12 m over the half): a suggestion with dots
    write_run(tmp_path, seconds=range(0, 600), kickoff=0, lineup=LINEUP, ours=ours, direction=-1)
    r = hr.build(tmp_path, 'm1')
    late = r['blocks']['thirds']['stretches'][-1]['dots']
    item = r['blocks']['next']['items'][0]
    assert item['dots'] == late
    lb = next(d for d in item['dots'] if d['role'] == 'LB')
    assert lb['v'] < 0 and lb['name'] == '선수1'
    assert r['blocks']['next']['direction'] == 1                                       # the second half attacks the other way on screen ...
    assert r['direction'] == -1                                                       # ... the picture is turned, the team's own left stays v < 0

def test_the_other_keeper_read_as_ours_is_dropped():
    ours = [(-20, 0), (-10, 5), (0, 0), (5, 10), (30.0, 2.0)]
    assert (30.0, 2.0) not in hr.drop_other_keeper(ours, 89.0)
    assert hr.drop_other_keeper([(-20, 0), (25, 0), (30, 2)], 89.0) == [(-20, 0), (25, 0), (30, 2)]   # a teammate within 10 m: kept


def test_address_without_session_shows_the_match_of_setup(tmp_path):
    """/halftime opened by its address alone: the report of the match started on /setup (same rule as the score board), never the newer files of an earlier match."""
    import os
    import time as _time
    write_run(tmp_path, session='old-match', seconds=range(0, 300), kickoff=0, alerts=[(100, 'conceded_run')])
    write_run(tmp_path, session='match-new', seconds=range(0, 300), kickoff=0)
    started = _time.time() - 60
    old_alerts = tmp_path / 'alerts' / 'old-match' / 'alerts.jsonl'
    os.utime(tmp_path / 'alerts' / 'match-new' / 'alerts.jsonl', (started - 600, started - 600))   # written before the match was started ...
    os.utime(old_alerts, (started - 10, started - 10))                                           # ... and the old match even later, but still before
    (tmp_path / 'service' / 'setup').mkdir(parents=True)
    (tmp_path / 'service' / 'setup' / 'match.json').write_text(json.dumps({'name': 'match-new', 'created': _time.strftime('%Y-%m-%dT%H:%M:%S', _time.localtime(started))}), encoding='utf-8')
    assert hr.current_session(tmp_path) == 'match-new'
    os.utime(old_alerts, None)                                                                  # a run written after the start (started by hand under another name) is the live one
    assert hr.current_session(tmp_path) == 'old-match'
    (tmp_path / 'service' / 'setup' / 'match.json').unlink()
    assert hr.current_session(tmp_path) == 'old-match'                                         # no match started: the newest live session
    origin = 'http://127.0.0.1:8443'
    client = TestClient(create_app(tmp_path, origin), base_url=origin)
    assert client.get('/api/v1/halftime/rich').json()['session'] == 'old-match'
    assert hr.current_session(tmp_path / 'nothing') is None


def test_width_is_the_spread_of_each_second_not_of_the_averaged_dots(tmp_path):
    """Team width = the full spread of the outfield players seen in each second, averaged (here -15 .. +15 m = 30 m); the 10-90 % spread is kept apart."""
    write_run(tmp_path, seconds=range(0, 600), kickoff=0)
    st = hr.build(tmp_path, 'm1')['blocks']['thirds']['stretches'][0]['means']
    assert st['width'] == 30.0 and st['vmin'] == -15.0 and st['vmax'] == 15.0
    assert st['width_p'] <= st['width']


def test_glance_lines_are_sentences_with_the_numbers_below(tmp_path):
    def ours(t):
        return team_points(-25.0 if t < 400 else -33.0)            # the back line sinks 8 m in the last stretch
    write_run(tmp_path, seconds=range(0, 600), kickoff=0, ours=ours, alerts=[(t, 'conceded_run') for t in (100, 300, 500)])
    r = hr.build(tmp_path, 'm1')
    lines = r['blocks']['glance']['lines']
    assert lines[0]['text'] == r['blocks']['next']['items'][0]['text']            # a suggestion of block 7 comes first
    assert all(len(x['text']) <= 40 and x['evidence'] for x in lines)
    assert not any('가장 낮음' in x['text'] or '가장 높음' in x['text'] for x in lines)   # the per-minute low and high mix attack and defence: never a line here
    assert sum('수비 줄' in x['text'] for x in lines) == 1                           # the same fact (block 2 and the suggestion) once
    assert any(x['text'].startswith('상대 침투 허용 알림이 가장 많았습니다') for x in lines)


# ---- the route and the page ----------------------------------------------------------------------------------------------------------
def test_route_page_and_bad_input(tmp_path):
    write_run(tmp_path, seconds=range(0, 600), kickoff=0, alerts=[(100, 'conceded_run')])
    origin = 'http://127.0.0.1:8443'
    client = TestClient(create_app(tmp_path, origin), base_url=origin)
    r = client.get('/api/v1/halftime/rich', params={'session': 'm1'}).json()
    assert r['state'] == 'running' and set(r['blocks']) == {'glance', 'thirds', 'line', 'sides', 'alerts', 'opponent', 'next'}
    assert client.get('/api/v1/halftime/rich', params={'session': '../x'}).status_code == 400
    assert client.get('/api/v1/halftime/rich', params={'session': 'm1', 'half': 3}).status_code == 400
    for page in ('/halftime', '/halftime.js', '/halftime.css'):
        assert client.get(page).status_code == 200
    assert client.get('/api/v1/halftime/rich', params={'session': 'none'}).json()['state'] == 'empty'


@pytest.mark.skipif(shutil.which('node') is None, reason='node not available')
def test_halftime_picture_direction_pure_functions():
    """Maps 2, 4, 5 and 6 are drawn in the direction of their half: the turn is a pure function (web/halftime.js HalftimeFlip)."""
    done = subprocess.run(['node', str(ROOT_DIR / 'tests' / 'test_halftime_flip.cjs')], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
