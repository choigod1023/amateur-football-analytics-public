"""Where the branches of 2026-11-24 meet (integration of polish, warmup, halftime-rich): the warm-up before the kick-off mark, restarts of the analysis before and during
the first half (several runs in one session, each counting its time from 0), the half-time sums of the band and the new report, and one rule for "the match now"."""
import json

from fastapi.testclient import TestClient

from app import bench_view, halftime_rich as hr, score_board
from app.review_public import create_app
from tests.test_halftime_rich import WALL, team_points, write_run

ORIGIN = 'http://127.0.0.1:8443'


def write_runs(store, runs, session='m1', tags=(), positions=True):
    """runs: [(wall of its second 0, seconds, direction, [(t, kind) alerts], keep positions)] in the order they ran. Positions of a run with keep=False went to the archive
    (a restart before the kick-off); its alert rows stay in alerts.jsonl, as on the server."""
    folder = store / 'alerts' / session
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / 'positions.jsonl', 'w', encoding='utf-8') as pos, open(folder / 'alerts.jsonl', 'w', encoding='utf-8') as al:
        for wall0, seconds, direction, alerts, keep in runs:
            if keep:
                pos.write(json.dumps({'type': 'header', 'team': 'B', 'other': 'A', 'direction': direction, 'pitch_length': 89.0, 'pitch_width': 62.0, 'first_second': 0.0}) + '\n')
                for t in seconds:
                    us = team_points(-25.0)
                    them = [(-u, -v) for u, v in team_points(-25.0)]
                    pos.write(json.dumps({'type': 'second', 'time': float(t), 'team': [[i, u * direction, v * direction] for i, (u, v) in enumerate(us)],
                                          'other': [[100 + i, u * direction, v * direction] for i, (u, v) in enumerate(them)]}) + '\n')
            for t in range(0, max(seconds) + 1, 5):
                al.write(json.dumps({'time': float(t), 'kind': 'heartbeat', 'type': 'heartbeat', 'polarity': 'status', 'wall': wall0 + t}) + '\n')
            for t, kind in alerts:
                al.write(json.dumps({'time': float(t), 'kind': kind, 'polarity': 'poor', 'title': kind}) + '\n')
    (store / 'analyst-tags').mkdir(exist_ok=True)
    (store / 'analyst-tags' / 'tags.jsonl').write_text(''.join(json.dumps({'op': 'add', 'id': f'x{i}', 'kind': k, 'epoch': e}) + '\n' for i, (k, e) in enumerate(tags)),
                                                       encoding='utf-8')
    return folder


def alert_total(report):
    return sum(k['count'] for k in report['blocks']['alerts']['kinds'])


# ---- a. the warm-up never reaches the first half ------------------------------------------------------------------------------------
def test_a_warm_up_300_s_then_600_s_half(tmp_path):
    """300 s of records with 5 alerts, the "전반 시작" mark, 600 s with 3 alerts, "전반 끝": only the 600 s and the 3 alerts count."""
    warm = [(t, 'conceded_run') for t in (30, 90, 150, 210, 270)]
    half = [(400, 'line_drop'), (600, 'line_drop'), (800, 'gap_wide')]
    write_run(tmp_path, seconds=range(0, 901), kickoff=300, end_tag=900, alerts=warm + half)
    r = hr.build(tmp_path, 'm1')
    assert (r['start_s'], r['end_s'], r['how_end']) == (300.0, 900.0, 'tag')
    assert alert_total(r) == 3
    assert {k['kind'] for k in r['blocks']['alerts']['kinds']} == {'line_drop', 'gap_wide'}


def test_a_band_button_and_report_use_the_same_end_and_direction(tmp_path):
    """"전반 끝 · 보고서 만들기" (POST /api/v1/halftime/start) fixes the end in the half-time state; the new report stops there and uses the direction of the same header."""
    write_run(tmp_path, seconds=range(0, 901), kickoff=300, direction=1, alerts=[(50, 'conceded_run'), (500, 'line_drop')])
    client = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    started = client.post('/api/v1/halftime/start', json={'session': 'm1'}, headers={'Origin': ORIGIN})
    assert started.status_code == 200, started.text
    old = client.get('/api/v1/halftime/report', params={'session': 'm1'}).json()
    rich = client.get('/api/v1/halftime/rich', params={'session': 'm1'}).json()
    assert rich['state'] == 'final'
    assert rich['end_s'] == old['end_s'] == 900.0
    assert rich['start_s'] == 300.0                       # the old sums start at the first second (warm-up included); /halftime shows only their two checks
    assert rich['direction'] == old['direction'] == 1
    assert alert_total(rich) == 1


# ---- b. restarts -------------------------------------------------------------------------------------------------------------------------
def test_b_restart_before_kickoff_with_archived_positions(tmp_path):
    """A 30-minute warm-up run (direction -1, 4 alerts), then the direction changed on /setup: positions.jsonl went to the archive, alerts.jsonl kept the warm-up rows.
    The new run (direction +1, its own seconds from 0) is the only one counted, with its own clock offset."""
    w1, w2 = WALL, WALL + 1900
    warm = [(200, 'conceded_run'), (400, 'conceded_run'), (600, 'conceded_run'), (800, 'conceded_run')]
    write_runs(tmp_path, [(w1, range(0, 1801), -1, warm, False), (w2, range(0, 801), 1, [(300, 'line_drop'), (500, 'line_drop')], True)],
               tags=[('start_h1', w2 + 100), ('end_h1', w2 + 700)])
    r = hr.build(tmp_path, 'm1')
    assert (r['start_s'], r['end_s'], r['how_end']) == (100.0, 700.0, 'tag')
    assert r['direction'] == 1 and r['direction_now'] == 1
    assert alert_total(r) == 2


def test_b_stop_and_start_with_another_direction_keeps_two_headers(tmp_path):
    """Stopped and started again by hand during the warm-up with the other direction: two header lines in positions.jsonl. Each run keeps the direction of its own header."""
    w1, w2 = WALL, WALL + 660
    write_runs(tmp_path, [(w1, range(0, 601), -1, [(300, 'conceded_run')], True), (w2, range(0, 1001), 1, [(200, 'line_drop'), (650, 'line_drop')], True)],
               tags=[('start_h1', w2 + 100), ('end_h1', w2 + 700)])
    r = hr.build(tmp_path, 'm1')
    assert r['direction'] == 1                            # not the -1 of the first header
    assert (r['start_s'], r['end_s']) == (760.0, 1360.0)   # the second run on the clock line of the first (+660 s)
    assert alert_total(r) == 2
    assert all(abs(st['means']['def'] - 19.5) < 0.01 for st in r['blocks']['thirds']['stretches'])   # the right direction: our back line 19.5 m from our goal line


def test_b_restart_during_the_first_half_keeps_both_parts(tmp_path):
    """The analysis stopped 400 s after the kick-off and was started again (same direction) 60 s later: both parts count, nothing of the new run is dropped as 'going back'."""
    w1, w2 = WALL, WALL + 560
    write_runs(tmp_path, [(w1, range(0, 501), -1, [(200, 'line_drop')], True), (w2, range(0, 601), -1, [(100, 'line_drop'), (300, 'gap_wide')], True)],
               tags=[('start_h1', w1 + 100), ('end_h1', w2 + 400)])
    r = hr.build(tmp_path, 'm1')
    assert (r['start_s'], r['end_s'], r['how_end']) == (100.0, 960.0, 'tag')
    assert sum(st['seconds'] for st in r['blocks']['thirds']['stretches']) == 401 + 401
    assert alert_total(r) == 3


def test_b_alert_runs_split_on_the_clock_offset():
    rows = [{'time': float(t), 'kind': 'heartbeat', 'wall': WALL + t} for t in range(0, 100, 5)] + [{'time': 50.0, 'kind': 'line_drop'}]
    rows += [{'time': float(t), 'kind': 'heartbeat', 'wall': WALL + 200 + t} for t in range(0, 50, 5)]
    runs = hr.alert_runs(rows)
    assert [len(r['numbers']) for r in runs] == [21, 10] and runs[1]['offset'] == WALL + 200
    assert hr.clock_offset(rows) == WALL + 200


# ---- c. one rule for the match now ----------------------------------------------------------------------------------------------------
def test_c_one_rule_for_the_match_now(tmp_path):
    write_run(tmp_path, session='match-a', seconds=range(0, 60))
    assert hr.current_session(tmp_path) == bench_view.live_session(tmp_path) == score_board.ScoreBoard(tmp_path).live_session() == 'match-a'
    assert hr.current_match is not None and hr.current_match(tmp_path) == bench_view.current_match(tmp_path) is None


def test_b_band_sums_follow_the_newest_header_too(tmp_path):
    """The half-time sums behind the band and the bench mini map (app/halftime_accumulator.py) read the direction of a later header as the new report does."""
    from app.halftime_accumulator import Accumulator
    w1, w2 = WALL, WALL + 660
    folder = write_runs(tmp_path, [(w1, range(0, 601), -1, [], True), (w2, range(0, 1001), 1, [], True)], tags=[('start_h1', w2 + 100)])
    acc = Accumulator('m1')
    acc.catch_up(folder / 'positions.jsonl', folder / 'alerts.jsonl')
    assert acc.current['direction'] == 1 == hr.build(tmp_path, 'm1')['direction_now']


def test_b_after_the_switch_a_later_header_does_not_turn_the_second_half(tmp_path):
    """Second half: the switch line holds the direction; a run started again later with the first-half direction in its header does not turn it back (as the band's sums)."""
    folder = tmp_path / 'alerts' / 'm1'
    folder.mkdir(parents=True)
    lines = [{'type': 'header', 'direction': 1, 'pitch_length': 89.0, 'pitch_width': 62.0}, {'type': 'second', 'time': 1.0, 'team': [], 'other': []},
             {'type': 'half', 'half': 2, 'direction': -1, 'time': 2.0}, {'type': 'header', 'direction': 1}, {'type': 'second', 'time': 0.5, 'team': [], 'other': []}]
    (folder / 'positions.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in lines), encoding='utf-8')
    runs = hr.read_position_runs(folder / 'positions.jsonl')
    assert [r[1] for run in runs for r in run['rows']] == [1, -1]


def test_d_second_half_without_a_half_line_uses_the_switch_sent_to_the_run(tmp_path):
    """"후반 시작" on the band writes the second-half command (control.jsonl) and the start_h2 mark; when the run has not written its 'half' line, the second-half report
    still uses the switched direction (the band's sums and the mini map do)."""
    folder = write_runs(tmp_path, [(WALL, range(0, 1201), -1, [], True)], tags=[('start_h1', WALL + 100), ('end_h1', WALL + 500), ('start_h2', WALL + 600)])
    (folder / 'control.jsonl').write_text(json.dumps({'seq': 1, 'cmd': 'second_half', 'direction': 1, 'at': WALL + 599}) + '\n', encoding='utf-8')
    r = hr.build(tmp_path, 'm1', half=2)
    assert r['start_s'] == 600.0 and r['direction'] == 1 and r['direction_now'] == 1
    assert hr.build(tmp_path, 'm1', half=1)['direction'] == -1
