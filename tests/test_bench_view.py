import json
import os

from app.bench_view import BenchView, accuracy_text, input_state, priority_of


def write_session(root, name, rows, mtime=None):
    folder = root / 'alerts' / name
    folder.mkdir(parents=True)
    path = folder / 'alerts.jsonl'
    path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def write_label(root, session, number, label):
    folder = root / 'alerts' / 'labels'
    folder.mkdir(parents=True, exist_ok=True)
    ident = f'{session}-{number}'
    (folder / f'{ident}.json').write_text(json.dumps({'id': ident, 'label': label}), encoding='utf-8')


def alert(kind, t=1.0, **extra):
    return {'time': t, 'kind': kind, 'polarity': 'poor', 'title': kind, 'text': f'text of {kind}', **extra}


def test_priority_follows_the_table_and_unknown_is_grey():
    assert priority_of({'kind': 'conceded_run'}) == 'urgent'
    assert priority_of({'kind': 'box_attack'}) == 'urgent'
    assert priority_of({'kind': 'isolated'}) == 'notice'
    assert priority_of({'kind': 'run'}) == 'notice'
    assert priority_of({'kind': 'line_drop'}) == 'info'
    assert priority_of({'kind': 'gap_wide'}) == 'info'
    assert priority_of({'kind': 'something_new'}) == 'info'
    assert priority_of({'kind': 'no_input', 'polarity': 'status'}) == 'urgent'


def test_accuracy_text_marks_a_small_sample():
    assert accuracy_text(0, 0) == '표본 적음 (판정 없음)'
    assert accuracy_text(3, 4) == '표본 적음 (판정 4개 중 3개 맞음)'
    assert accuracy_text(8, 9) == '판정 9개 중 8개 맞음'


def test_input_state_from_status_rows_and_heartbeats():
    rows = [alert('run'), {'kind': 'no_input', 'polarity': 'status'}]
    assert input_state(rows, [100.0, 105.0], 110.0)['state'] == 'no_input'
    rows.append({'kind': 'input_back', 'polarity': 'status'})
    assert input_state(rows, [100.0, 105.0, 108.0], 110.0)['state'] == 'unknown'          # no heartbeat rows: the file alone says nothing
    beats = [{'type': 'heartbeat'}, {'type': 'heartbeat'}]
    assert input_state(beats, [100.0, 104.0], 108.0)['state'] == 'ok'
    assert input_state(beats, [100.0, 104.0], 130.0)['state'] == 'no_input'
    assert input_state([None], [1.0], 2.0)['state'] == 'unknown'


def test_snapshot_without_a_store_says_nothing_to_show(tmp_path):
    shot = BenchView(tmp_path).snapshot()
    assert shot['current'] is None and shot['recent'] == [] and shot['session'] is None


def test_snapshot_shows_newest_alert_five_before_and_accuracy(tmp_path):
    kinds = ['run', 'isolated', 'box_attack', 'line_drop', 'gap_wide', 'conceded_run', 'box_attack']
    write_session(tmp_path, 'live1', [alert(k, i) for i, k in enumerate(kinds)], mtime=1000.0)
    write_session(tmp_path, 'rated', [alert('box_attack', i) for i in range(6)], mtime=900.0)
    for number, label in enumerate(['ok', 'ok', 'ok', 'wrong', 'useless', 'ok']):
        write_label(tmp_path, 'rated', number, label)
    clock = iter([1010.0, 1012.0])
    view = BenchView(tmp_path, clock=lambda: next(clock))
    first = view.snapshot()
    assert first['session'] == 'live1'
    assert first['current']['kind'] == 'box_attack' and first['current']['priority'] == 'urgent'
    assert [a['kind'] for a in first['recent']] == ['conceded_run', 'gap_wide', 'line_drop', 'box_attack', 'isolated']
    assert first['current']['age_estimated'] is True and first['current']['age_s'] == 10.0          # a row that was there at the first read gets the time of the file
    assert first['current']['accuracy']['total'] == 6 and first['current']['accuracy']['ok'] == 4
    assert first['current']['accuracy']['text'] == '판정 6개 중 4개 맞음'
    assert first['recent'][1]['accuracy']['low_sample'] is True                                    # gap_wide was never rated
    with open(tmp_path / 'alerts' / 'live1' / 'alerts.jsonl', 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(alert('isolated', 9.0)) + '\n')
    second = view.snapshot()
    assert second['current']['kind'] == 'isolated' and second['current']['age_estimated'] is False and second['current']['age_s'] == 0.0


def test_review_sessions_and_status_rows_do_not_count_as_live_alerts(tmp_path):
    write_session(tmp_path, 'pictures', [{'time': 1.0, 'kind': 'person_check', 'title': 'x', 'text': 'y'}] * 3, mtime=2000.0)
    write_session(tmp_path, 'live2', [alert('run'), {'time': 3.0, 'kind': 'no_input', 'polarity': 'status', 'title': '입력 없음', 'text': '끊김'}], mtime=1000.0)
    write_label(tmp_path, 'pictures', 0, 'ok')
    write_label(tmp_path, 'live2', 1, 'ok')
    shot = BenchView(tmp_path, clock=lambda: 1005.0).snapshot()
    assert shot['session'] == 'live2'                       # the newer file is a picture-rating session, not a live run
    assert shot['current']['status'] is True and shot['current']['accuracy'] is None
    assert shot['state']['state'] == 'no_input'
    assert shot['accuracy'] == {}                           # ratings of a status row and of a picture session are left out
    assert BenchView(tmp_path, clock=lambda: 1005.0).snapshot(session='pictures')['session'] is None          # a named session that is not a live run is not shown


def test_damaged_lines_and_labels_are_skipped(tmp_path):
    folder = tmp_path / 'alerts' / 'live3'
    folder.mkdir(parents=True)
    (folder / 'alerts.jsonl').write_text('not json\n' + json.dumps(alert('run')) + '\n', encoding='utf-8')
    (tmp_path / 'alerts' / 'labels').mkdir()
    (tmp_path / 'alerts' / 'labels' / 'live3-1.json').write_text('{broken', encoding='utf-8')
    shot = BenchView(tmp_path, clock=lambda: 50.0).snapshot()
    assert shot['current']['kind'] == 'run' and shot['accuracy'] == {}


def test_routes_serve_the_page_and_the_snapshot(tmp_path):
    from fastapi.testclient import TestClient
    from app.review_public import create_app
    write_session(tmp_path, 'live4', [alert('conceded_run')])
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    for path in ('/bench', '/bench.js', '/bench.css'):
        assert client.get(path).status_code == 200
    data = client.get('/api/v1/bench').json()
    assert data['current']['kind'] == 'conceded_run' and data['session'] == 'live4'
    assert client.get('/api/v1/bench', params={'session': 'x' * 80}).status_code == 200
    assert client.post('/api/v1/bench', headers={'origin': 'http://example.test'}).status_code == 405                    # read only: there is no way to write through this route
