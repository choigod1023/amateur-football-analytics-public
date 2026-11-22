import json
import os
import time

from fastapi.testclient import TestClient

from app.halftime_accumulator import Accumulator, match_slots, merge_doubles
from app.halftime_report import HalftimeService, build_report
from app.live_control import ControlWatcher
from app.live_input import heartbeat_record
from app.live_positions import PositionLog
from app.review_public import create_app
from app.service_watch import ServiceWatch


def squad(front, flip=1):
    xs = [front - 4 * i for i in range(10)]
    return [(i + 1, x * flip, ((i * 11) % 40) - 20) for i, x in enumerate(xs)] + [(11, -42.0 * flip, 0.0)]


def make_run(tmp_path, seconds=range(0, 600), skip=(), session='s1', direction=1, seen=11, alerts=True):
    folder = tmp_path / 'alerts' / session
    folder.mkdir(parents=True, exist_ok=True)
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', direction, 89.0, 62.0, 0.0)
    for t in seconds:
        if t in skip:
            continue
        ours = squad(10.0 + (t % 20), flip=direction)[:seen]
        theirs = [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(5.0, flip=direction))][:seen]
        log.add(float(t), ours, theirs)
    log.close()
    if alerts:
        rows = [{'time': 30.0, 'kind': 'box_attack', 'polarity': 'good', 'title': '박스 침투', 'text': 'x'}, {'time': 90.0, 'kind': 'box_attack', 'polarity': 'good', 'title': '박스 침투', 'text': 'x'},
                {'time': 120.0, 'kind': 'conceded_run', 'polarity': 'poor', 'title': '침투 허용', 'text': 'y'}, {'time': 130.0, 'kind': 'no_input', 'polarity': 'status', 'title': '입력 없음', 'text': 'z'},
                heartbeat_record(5.0, {})]
        (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    return folder


def accumulate(folder):
    acc = Accumulator('s1')
    acc.catch_up(folder / 'positions.jsonl', folder / 'alerts.jsonl')
    return acc


def test_slots_are_matched_to_the_closest_free_slot_and_extra_players_are_dropped():
    reference = [(float(i * 10), 0.0) for i in range(11)]
    assert match_slots([(0.0, 1.0), (50.0, 1.0), (100.0, 1.0)], reference) == [0, 5, 10]
    assert match_slots([(float(i * 10) + 1, 0.0) for i in range(11)] + [(200.0, 40.0)], reference)[-1] == -1
    assert match_slots([(0.0, 0.0), (0.4, 0.2)], reference) == [0, 1]          # two players near one slot: the second takes the next free one
    assert merge_doubles([(1, 0.0, 0.0), (2, 0.5, 0.5), (3, 5.0, 5.0)]) == [(1, 0.0, 0.0), (3, 5.0, 5.0)]


def test_the_sums_grow_line_by_line_and_equal_the_sums_of_one_read(tmp_path):
    folder = make_run(tmp_path, range(0, 300))
    whole = accumulate(folder)
    text = (folder / 'positions.jsonl').read_bytes()
    part = tmp_path / 'part.jsonl'
    acc = Accumulator('s1')
    cut = 0
    for size in (500, 4000, 9000, len(text)):
        part.write_bytes(text[:size])                                                # a cut in the middle of a line leaves the half line unread
        acc.catch_up(part, None)
        assert acc.state['pos_offset'] <= size and part.read_bytes()[:acc.state['pos_offset']].endswith(b'\n')
    assert acc.state['halves']['1']['seconds'] == whole.state['halves']['1']['seconds'] == 300
    assert acc.state['halves']['1']['minutes'] == whole.state['halves']['1']['minutes']


def test_the_sums_are_saved_and_a_restart_goes_on_from_the_saved_offset(tmp_path):
    folder = make_run(tmp_path, range(0, 100))
    acc = accumulate(folder)
    acc.save(tmp_path / 'accum.json')
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', 1, 89.0, 62.0, 0.0)          # the run goes on (a second header line is ignored)
    for t in range(100, 160):
        log.add(float(t), squad(10.0), squad(5.0))
    log.close()
    again = Accumulator.load('s1', tmp_path / 'accum.json')
    assert again.state['halves']['1']['seconds'] == 100
    again.catch_up(folder / 'positions.jsonl', None)
    assert again.state['halves']['1']['seconds'] == 160


def test_the_report_is_in_coach_words_without_developer_numbers(tmp_path):
    acc = accumulate(make_run(tmp_path, range(0, 600), skip=range(200, 260)))
    report = build_report({**acc.state, 'session': 's1'}, 1, None, 'coach')
    text = json.dumps({k: report[k] for k in ('summary', 'problems', 'second_half', 'missing')}, ensure_ascii=False)
    for word in ('검출', 'm 앞', '미터', 'fps', 'track', '추정'):
        assert word not in text
    assert report['missing']['ranges'] == [{'from_text': '3분 21초', 'to_text': '4분 20초', 'length_text': '59초'}] or report['missing']['ranges'][0]['to_text'] == '4분 20초'
    assert report['missing']['share_word'] == '꽤 많이' and any('영상이 끊긴 구간이 1곳' in line for line in report['summary'])
    counts = {a['title']: a['count'] for a in report['alerts']}
    assert counts == {'박스 침투': 2, '침투 허용': 1}                              # status rows and heartbeats are not alerts
    assert report['second_half'][0].startswith('공격 방향 확인') and '화면 오른쪽' in report['second_half'][0] and report['second_half'][1].startswith('팀 색 재확인')
    assert report['build_seconds'] < 1.0


def test_both_teams_are_drawn_with_eleven_players_also_when_only_nine_are_seen(tmp_path):
    folder = make_run(tmp_path, range(0, 200))                                       # 200 s with all 11 players first: the roles are made
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', 1, 89.0, 62.0, 0.0)
    for t in range(200, 500):
        ours = [p for p in squad(10.0 + (t % 20)) if p[0] not in (3, 7)]              # two of our players and two of theirs are never seen again
        theirs = [(100 + i, -x, y) for i, (_k, x, y) in enumerate(squad(5.0)) if i not in (2, 8)]
        log.add(float(t), ours, theirs)
    log.close()
    acc = accumulate(folder)
    report = build_report({**acc.state, 'session': 's1'})
    assert report['pictures'] and all(len(p['ours']) == 11 and len(p['theirs']) == 11 for p in report['pictures'])


def test_runs_into_the_box_and_runs_the_other_team_made_are_found_second_by_second(tmp_path):
    folder = tmp_path / 'alerts' / 's1'
    folder.mkdir(parents=True)
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', 1, 89.0, 62.0, 0.0)
    for t in range(0, 120):
        ours = [(i + 1, -30.0 + 3 * i, -15.0 + 3 * i) for i in range(11)]
        if 40 <= t <= 46:                                                            # three of ours in the box of the goal they attack
            ours[8], ours[9], ours[10] = (9, 33.0, -5.0), (10, 35.0, 0.0), (11, 36.0, 6.0)
        theirs = [(100 + i, 20.0 - 3 * i, -15.0 + 3 * i) for i in range(11)]
        theirs[0] = (100, -10.0 - 6.0 * max(0, t - 70) if t < 75 else -40.0, 0.0)    # one of theirs runs 6 m a second towards our goal over 4 s from second 70
        log.add(float(t), ours, theirs)
    log.close()
    report = build_report({**accumulate(folder).state, 'session': 's1'})
    assert report['box_total'] >= 1 and report['box_attacks'][0]['time_text'] == '0분 40초' and '3명' in report['box_attacks'][0]['text']
    assert report['conceded_total'] >= 1 and '뛰어들었습니다' in report['conceded'][0]['text']


def test_the_direction_check_notices_a_wrong_direction(tmp_path):
    folder = make_run(tmp_path, range(0, 120), direction=1)
    path = folder / 'positions.jsonl'
    path.write_text(path.read_text(encoding='utf-8').replace('"direction": 1', '"direction": -1', 1), encoding='utf-8')
    report = build_report({**accumulate(folder).state, 'session': 's1'})
    assert '입력한 방향과 반대쪽' in report['second_half'][0]


def test_the_second_half_starts_new_sums_keeps_the_first_and_tells_the_live_run(tmp_path):
    folder = make_run(tmp_path, range(0, 200))
    service = HalftimeService(tmp_path)
    assert service.switch_second_half('s1') == -1                                    # the first half attacked to the right (+1)
    assert service.switch_second_half('s1') is None                                  # pressing twice does nothing
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', 1, 89.0, 62.0, 0.0)
    for t in range(200, 260):
        log.add(float(t), squad(-10.0, flip=-1), squad(-5.0, flip=-1))
    log.close()
    service.refresh('s1', force=True)
    state = service.accumulator('s1').state
    assert state['half'] == 2 and state['halves']['1']['seconds'] == 200 and state['halves']['2']['seconds'] == 60 and state['halves']['2']['direction'] == -1
    commands = [json.loads(l) for l in (folder / 'control.jsonl').read_text(encoding='utf-8').splitlines()]
    assert commands == [{'seq': 1, 'cmd': 'second_half', 'direction': -1, 'at': commands[0]['at']}]
    status = service.status('s1')
    assert status['second_half']['colour_checked'] is False and status['second_half']['attack_text'] == '화면 왼쪽'
    assert service.colour_checked('s1') and service.status('s1')['second_half']['colour_checked'] is True
    assert service.second_half_report('s1')['half'] == 2
    assert Accumulator.load('s1', tmp_path / 'service' / 'halftime' / 's1' / 'accum.json').state['half'] == 2


def test_a_half_line_written_by_the_live_run_starts_the_second_half(tmp_path):
    folder = make_run(tmp_path, range(0, 100))
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', 1, 89.0, 62.0, 0.0)
    log.write({'type': 'half', 'half': 2, 'direction': -1, 'time': 100.0})
    log.add(101.0, squad(-10.0, flip=-1), squad(-5.0, flip=-1))
    log.close()
    state = accumulate(folder).state
    assert state['half'] == 2 and state['halves']['2']['seconds'] == 1 and state['halves']['1']['seconds'] == 100


def test_the_control_watcher_ignores_old_commands_and_bad_ones(tmp_path):
    path = tmp_path / 'control.jsonl'
    path.write_text(json.dumps({'seq': 1, 'cmd': 'second_half', 'direction': 1}) + '\n', encoding='utf-8')
    watcher = ControlWatcher(path)
    assert watcher.poll() == []                                                      # a command from before the start is not executed again
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write('not json\n' + json.dumps({'seq': 2, 'cmd': 'second_half', 'direction': 5}) + '\n' + json.dumps({'seq': 3, 'cmd': 'second_half', 'direction': -1}) + '\n')
    assert [c['seq'] for c in watcher.poll()] == [3] and watcher.poll() == []
    assert ControlWatcher(tmp_path / 'none.jsonl').poll() == []


def test_the_report_waits_for_a_person_and_is_made_from_the_sums_on_the_button(tmp_path):
    make_run(tmp_path, range(0, 300))
    service = HalftimeService(tmp_path, ServiceWatch(tmp_path))
    assert service.status('s1')['status'] == 'waiting'
    done = service.start('s1', None, 'coach')
    assert done['status'] == 'ready' and service.report('s1')['end_text'] == '4분 59초' and done['build_seconds'] < 1.0
    assert service.status('s1')['link'] == '/halftime?session=s1'


def test_an_outage_late_in_the_first_half_makes_a_draft_at_once_and_a_person_confirms_or_refuses(tmp_path):
    folder = make_run(tmp_path, range(0, 300))
    old = time.time() - 600
    os.utime(folder / 'alerts.jsonl', (old, old))                                    # the heartbeat is silent and the process does not exist
    watch = ServiceWatch(tmp_path, pid_check=lambda pid: False)
    service = HalftimeService(tmp_path, watch, half_seconds=360.0)                   # a half of 6 minutes: 300 s is late enough
    watch.poll()
    assert watch.open
    assert service.tick() == 's1'
    status = service.status('s1')
    assert status['status'] == 'ready' and status['source'] == 'auto' and service.report('s1')['source'] == 'auto'
    assert '자동으로 만들었습니다' in service.report('s1')['source_text']
    assert service.confirm('s1') and service.report('s1')['source'] == 'confirmed' and service.status('s1')['source'] == 'confirmed'
    service2 = HalftimeService(tmp_path, watch, half_seconds=360.0)
    service2.dismiss('s1')                                                           # a confirmed report is not thrown away by a refusal
    assert service2.report('s1')['source'] == 'confirmed'


def test_a_refused_draft_is_deleted_and_not_made_again_for_the_same_stop(tmp_path):
    folder = make_run(tmp_path, range(0, 300))
    old = time.time() - 600
    os.utime(folder / 'alerts.jsonl', (old, old))
    watch = ServiceWatch(tmp_path, pid_check=lambda pid: False)
    service = HalftimeService(tmp_path, watch, half_seconds=360.0)
    watch.poll()
    service.tick()
    assert service.dismiss('s1') and service.report('s1') is None
    service.tick()
    assert service.report('s1') is None and service.status('s1')['status'] == 'waiting'


def test_a_short_stop_early_in_the_half_makes_nothing(tmp_path):
    folder = make_run(tmp_path, range(0, 60))
    old = time.time() - 600
    os.utime(folder / 'alerts.jsonl', (old, old))
    watch = ServiceWatch(tmp_path, pid_check=lambda pid: False)
    service = HalftimeService(tmp_path, watch, half_seconds=2700.0)
    watch.poll()
    service.tick()
    assert service.report('s1') is None


def test_a_long_hole_late_in_the_run_is_offered_as_the_end_and_a_refusal_is_remembered(tmp_path):
    make_run(tmp_path, list(range(0, 220)) + list(range(300, 340)), alerts=False)
    service = HalftimeService(tmp_path, None, half_seconds=270.0)
    service.refresh('s1')
    suggestion = service.status('s1')
    assert suggestion['status'] == 'suggested' and suggestion['end_s'] == 219.0
    service.dismiss('s1', suggestion['end_s'])
    assert service.status('s1')['status'] == 'waiting'
    done = service.start('s1', suggestion['end_s'], 'confirmed')
    assert done['status'] == 'ready' and service.report('s1')['source'] == 'confirmed' and service.report('s1')['end_text'] == '3분 39초'


def test_a_session_without_positions_says_how_to_start_the_run(tmp_path):
    folder = tmp_path / 'alerts' / 's1'
    folder.mkdir(parents=True)
    (folder / 'alerts.jsonl').write_text('{"time": 1, "kind": "box_attack"}\n', encoding='utf-8')
    service = HalftimeService(tmp_path)
    assert service.status('s1')['status'] == 'no_positions'
    try:
        service.start('s1', None, 'coach')
    except ValueError as error:
        assert '자료' in str(error)
    else:
        raise AssertionError('a report without positions must be refused')


def test_routes_pages_and_the_origin_rule(tmp_path):
    make_run(tmp_path, range(0, 200))
    origin = 'http://127.0.0.1:8443'
    client = TestClient(create_app(tmp_path, origin), base_url=origin)
    for page in ('/watch', '/halftime', '/watch-banner.js', '/watch.js', '/halftime.js', '/bench'):
        assert client.get(page).status_code == 200
    assert 'watch-banner.js' in client.get('/bench').text
    assert client.get('/api/v1/service').json()['state'] in ('ok', 'unknown', 'idle', 'down')
    assert client.get('/api/v1/halftime/report', params={'session': 's1'}).status_code == 404
    assert client.get('/api/v1/halftime', params={'session': '../x'}).status_code == 400
    assert client.post('/api/v1/halftime/start', json={'session': 's1'}).status_code == 403          # no origin header
    headers = {'Origin': origin}
    assert client.post('/api/v1/halftime/start', json={'session': 's1'}, headers=headers).status_code == 200
    report = client.get('/api/v1/halftime/report', params={'session': 's1'})
    assert report.status_code == 200 and report.json()['end_text'] == '3분 19초'
    switched = client.post('/api/v1/halftime/second-half', json={'session': 's1'}, headers=headers).json()
    assert switched == {'switched': True, 'direction': -1}
    assert client.post('/api/v1/halftime/second-half', json={'session': 's1'}, headers=headers).json()['switched'] is False
    assert client.post('/api/v1/halftime/colour-checked', json={'session': 's1'}, headers=headers).json() == {'checked': True}
    assert client.post('/api/v1/service/ack', json={'session': 's1', 'extra': 1}, headers=headers).status_code == 422
