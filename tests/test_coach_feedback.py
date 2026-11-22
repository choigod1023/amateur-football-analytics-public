import json

import pytest
from fastapi.testclient import TestClient

from app.coach_feedback import CoachFeedback, latest_positions
from app.halftime_accumulator import Accumulator
from app.halftime_report import build_report
from app.lineup import load_lineup
from app.live_input import heartbeat_record, status_record
from app.live_positions import PositionLog
from app.review_public import create_app

ORIGIN = 'http://127.0.0.1:8443'


def alert(kind='box_attack', t=1.0):
    return {'time': t, 'kind': kind, 'polarity': 'poor', 'title': kind, 'text': 'x'}


def make_session(tmp_path, name='s1'):
    folder = tmp_path / 'alerts' / name
    folder.mkdir(parents=True)
    rows = [heartbeat_record(1.0, {}), alert('box_attack'), status_record('no_input', 3.0), alert('conceded_run', 4.0), alert('box_attack', 5.0)]
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    return folder


def write_user_label(tmp_path, session, number, label):
    folder = tmp_path / 'alerts' / 'labels'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{session}-{number}.json'
    path.write_text(json.dumps({'id': f'{session}-{number}', 'label': label}), encoding='utf-8')
    return path


def test_a_coach_answer_is_saved_apart_with_its_origin_and_can_be_replaced(tmp_path):
    make_session(tmp_path)
    feedback = CoachFeedback(tmp_path)
    record = feedback.set('s1', 1, 'ok')
    assert record['origin'] == 'coach_button' and (tmp_path / 'alerts' / 'labels-coach' / 's1-1.json').is_file()
    assert not (tmp_path / 'alerts' / 'labels').exists()                       # the folder of the reviewer's ratings was not even made
    feedback.set('s1', 1, 'wrong')
    assert feedback.coach_label('s1', 1) == 'wrong' and len(list((tmp_path / 'alerts' / 'labels-coach').glob('*.json'))) == 1


@pytest.mark.parametrize('session,number,label', [('../x', 1, 'ok'), ('s1', -1, 'ok'), ('s1', 100000, 'ok'), ('s1', True, 'ok'), ('s1', 1, 'useless'), ('s1', 1, 'OK'),
                                                   ('s1', 0, 'ok'), ('s1', 2, 'ok'), ('s1', 99, 'ok'), ('nope', 1, 'ok'), ('s1', '1', 'ok')])
def test_wrong_input_is_refused_and_nothing_is_written(tmp_path, session, number, label):
    make_session(tmp_path)                                                      # row 0 is a heartbeat and row 2 a status row: not alerts
    feedback = CoachFeedback(tmp_path)
    with pytest.raises(ValueError):
        feedback.set(session, number, label)
    assert not (tmp_path / 'alerts' / 'labels-coach').exists()


def test_the_reviewer_wins_and_his_files_are_never_touched(tmp_path):
    make_session(tmp_path)
    user_file = write_user_label(tmp_path, 's1', 1, 'wrong')
    before = user_file.read_bytes()
    feedback = CoachFeedback(tmp_path)
    feedback.set('s1', 1, 'ok')                                                # the same alert, the opposite answer
    feedback.set('s1', 3, 'ok')
    feedback.set('s1', 4, 'wrong')
    assert user_file.read_bytes() == before and [p.name for p in (tmp_path / 'alerts' / 'labels').iterdir()] == ['s1-1.json']
    state = feedback.state('s1', [1, 3, 4])
    assert state[1] == {'coach': 'ok', 'user': 'wrong'} and state[3] == {'coach': 'ok', 'user': None}
    summary = feedback.summary('s1')
    assert summary == {'kinds': {'conceded_run': {'ok': 1, 'wrong': 0}, 'box_attack': {'ok': 0, 'wrong': 1}}, 'left_out': 1}


def test_routes_check_the_origin_and_the_values_and_report_both_ratings(tmp_path):
    make_session(tmp_path)
    write_user_label(tmp_path, 's1', 4, 'ok')
    client = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    body = {'session': 's1', 'number': 1, 'label': 'ok'}
    assert client.post('/api/v1/bench/feedback', json=body).status_code == 403                    # no origin
    headers = {'Origin': ORIGIN}
    assert client.post('/api/v1/bench/feedback', json=body, headers=headers).json() == {'saved': True, 'label': 'ok', 'origin': 'coach_button', 'user': None}
    for bad in ({**body, 'label': 'useless'}, {**body, 'number': -3}, {**body, 'number': 100000}, {**body, 'extra': 1}, {**body, 'session': ''}):
        assert client.post('/api/v1/bench/feedback', json=bad, headers=headers).status_code == 422
    assert client.post('/api/v1/bench/feedback', json={**body, 'number': 0}, headers=headers).status_code == 409           # a heartbeat is not an alert
    state = client.get('/api/v1/bench/feedback', params={'session': 's1', 'numbers': '1,4'}).json()
    assert state['labels']['1'] == {'coach': 'ok', 'user': None} and state['labels']['4']['user'] == 'ok'
    assert client.get('/api/v1/bench/feedback', params={'session': '../x'}).status_code == 400
    assert client.get('/bench-extra.js').status_code == 200 and 'bench-extra.js' in client.get('/bench').text


def positions_file(tmp_path, count=40, direction=1):
    folder = tmp_path / 'alerts' / 's1'
    folder.mkdir(parents=True, exist_ok=True)
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', direction, 89.0, 62.0, 0.0)
    for t in range(count):
        ours = [(i + 1, (-30.0 + 5 * i) * direction, (-6.0 if i < 3 else 14.0) * direction) for i in range(11)]       # the four deepest all stand in the right lane
        log.add(float(t), ours, [(100 + i, (30.0 - 5 * i) * direction, 3.0 * direction) for i in range(11)])
    log.close()
    return folder / 'positions.jsonl'


def test_the_small_map_reads_the_end_of_the_file_and_names_the_empty_side(tmp_path):
    path = positions_file(tmp_path)
    result = latest_positions(path, None)
    assert result['time'] == 39.0 and len(result['ours']) == 11 and len(result['theirs']) == 11 and result['team'] == 'B'
    assert result['empty'] == ['left']                                           # the lane under the deepest players that nobody covers: in this made-up shape v = -6 is the centre, so the left lane is free
    flipped = latest_positions(positions_file(tmp_path / 'x', direction=-1), None)
    assert flipped['ours'] == result['ours']                                     # the picture is always drawn with our team attacking to the right


def test_the_map_route_and_a_missing_file(tmp_path):
    client = TestClient(create_app(tmp_path, ORIGIN), base_url=ORIGIN)
    assert client.get('/api/v1/bench/minimap').json() == {'session': None}
    positions_file(tmp_path)
    (tmp_path / 'alerts' / 's1' / 'alerts.jsonl').write_text(json.dumps(heartbeat_record(1.0, {})) + '\n', encoding='utf-8')
    answer = client.get('/api/v1/bench/minimap').json()
    assert answer['session'] == 's1' and len(answer['positions']['ours']) == 11
    assert latest_positions(tmp_path / 'none.jsonl') is None


def entry_run(tmp_path, side_y, seconds=300):
    folder = tmp_path / 'alerts' / 's1'
    folder.mkdir(parents=True, exist_ok=True)
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', 1, 89.0, 62.0, 0.0)
    for t in range(seconds):
        ours = [(i + 1, -20.0 + 4 * i, -16.0 + 3 * i) for i in range(11)]
        theirs = [(100 + i, 30.0 - 2 * i, -16.0 + 3 * i) for i in range(11)]
        if t % 30 < 6:                                                           # every 30 s one of theirs comes into our defensive third (x within 30 m of our goal line at -44.5)
            theirs[0] = (100, -25.0, side_y)
        else:
            theirs[0] = (100, 30.0, side_y)
        log.add(float(t), ours, theirs)
    log.close()
    return folder


def test_entries_of_the_other_team_are_counted_once_per_ten_seconds_and_said_in_words(tmp_path):
    folder = entry_run(tmp_path, 0.0)
    acc = Accumulator('s1')
    acc.catch_up(folder / 'positions.jsonl', None)
    entries = acc.state['halves']['1']['entries']
    assert len(entries) == 10 and all(e[1] == 1 for e in entries)                # ten visits in 300 s, all through the centre
    report = build_report({**acc.state, 'session': 's1'})
    assert report['opponent'][0] == '상대가 우리 수비 지역에 자주 들어왔습니다.' and '가운데로 가장 많이 들어왔습니다' in report['opponent'][1]
    assert any('상대가 우리 수비 지역에 자주' in line for line in report['summary'])
    text = json.dumps(report['opponent'], ensure_ascii=False)
    assert '공을' not in text and not any(ch.isdigit() for ch in text)           # no numbers and nothing about the ball


def test_entries_say_which_side_and_a_quiet_half_says_so(tmp_path):
    folder = entry_run(tmp_path, 16.0)                                           # our team attacks +x: y = +16 is the team's own right
    acc = Accumulator('s1')
    acc.catch_up(folder / 'positions.jsonl', None)
    assert '오른쪽으로 가장 많이 들어왔습니다' in build_report({**acc.state, 'session': 's1'})['opponent'][1]
    calm = tmp_path / 'calm'
    folder = calm / 'alerts' / 's1'
    folder.mkdir(parents=True)
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', 1, 89.0, 62.0, 0.0)
    for t in range(120):
        log.add(float(t), [(i + 1, -20.0 + 4 * i, -16.0 + 3 * i) for i in range(11)], [(100 + i, 30.0 - 2 * i, -16.0 + 3 * i) for i in range(11)])
    log.close()
    acc = Accumulator('s1')
    acc.catch_up(folder / 'positions.jsonl', None)
    assert build_report({**acc.state, 'session': 's1'})['opponent'] == ['상대가 우리 수비 지역 가까이 들어오는 일은 거의 없었습니다.']


def test_the_lineup_is_shown_only_when_a_person_typed_it_and_exactly_as_typed(tmp_path):
    folder = entry_run(tmp_path, 0.0, 120)
    acc = Accumulator('s1')
    acc.catch_up(folder / 'positions.jsonl', None)
    assert load_lineup(tmp_path) is None and 'lineup' not in build_report({**acc.state, 'session': 's1'}, lineup=load_lineup(tmp_path))
    (tmp_path / 'service').mkdir()
    typed = {'formation': '3-4-1-2', 'players': [{'role': 'GK', 'name': '가나다', 'note': '공중볼 먼저'}, {'role': 'CB', 'name': 'x' * 50}, {'role': '', 'name': '빈 역할'}, 'garbage']}
    (tmp_path / 'service' / 'lineup.json').write_text(json.dumps(typed, ensure_ascii=False), encoding='utf-8')
    lineup = load_lineup(tmp_path)
    assert lineup == {'formation': '3-4-1-2', 'players': [{'role': 'GK', 'name': '가나다', 'note': '공중볼 먼저'}, {'role': 'CB', 'name': 'x' * 20, 'note': ''}]}
    report = build_report({**acc.state, 'session': 's1'}, lineup=lineup)
    assert report['lineup'] == lineup and any('계획한 모양은 3-4-1-2입니다' in line for line in report['second_half'])
    assert all('가나다' not in json.dumps(p, ensure_ascii=False) for p in report['pictures'])      # no name is attached to a dot
    (tmp_path / 'service' / 'lineup.json').write_text('not json', encoding='utf-8')
    assert load_lineup(tmp_path) is None
    (tmp_path / 'service' / 'lineup.json').write_text(json.dumps({'players': []}), encoding='utf-8')
    assert load_lineup(tmp_path) is None
