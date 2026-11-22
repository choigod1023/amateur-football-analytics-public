import json
import os
import subprocess
import sys
import time

from app.live_input import heartbeat_record, status_record
from app.service_watch import ServiceWatch, length_text, pid_alive


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def write_rows(root, session, rows, at):
    folder = root / 'alerts' / session
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'alerts.jsonl'
    path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    os.utime(path, (at, at))


def beat(pid=4242):
    return {**heartbeat_record(5.0, {}), 'pid': pid}


def make(tmp_path, alive=True):
    clock = Clock()
    state = {'alive': alive}
    watch = ServiceWatch(tmp_path, clock=clock, pid_check=lambda pid: state['alive'])
    return watch, clock, state


def test_a_run_with_fresh_heartbeats_is_ok_and_nothing_is_logged(tmp_path):
    watch, clock, _ = make(tmp_path)
    write_rows(tmp_path, 's1', [beat()], clock.now - 3)
    picture = watch.poll()
    assert picture['state'] == 'ok' and picture['outages'] == [] and not (tmp_path / 'service' / 'outages.jsonl').exists()


def test_a_quiet_file_without_heartbeats_is_unknown_and_never_an_outage(tmp_path):
    watch, clock, _ = make(tmp_path)
    write_rows(tmp_path, 's1', [{'time': 1.0, 'kind': 'box_attack', 'polarity': 'poor', 'title': 'x', 'text': 'y'}], clock.now - 600)
    assert watch.poll()['state'] == 'unknown'


def test_silent_heartbeat_with_a_living_process_is_a_lost_input_and_recovery_is_logged(tmp_path):
    watch, clock, _ = make(tmp_path)
    write_rows(tmp_path, 's1', [beat()], clock.now - 3)
    assert watch.poll()['state'] == 'ok'
    clock.now += 40                                                     # 43 s since the last change
    down = watch.poll()
    assert down['state'] == 'down' and down['cause'] == 'video_lost' and down['headline'] == '영상 입력 끊김'
    assert down['since'] == clock.now - 43 and down['duration_s'] == 43.0
    clock.now += 17
    assert watch.poll()['duration_s'] == 60.0 and len(watch.listing()) == 1
    write_rows(tmp_path, 's1', [beat(), beat()], clock.now - 1)         # the run writes again
    up = watch.poll()
    assert up['state'] == 'ok' and up['outages'][0]['open'] is False and up['outages'][0]['end_reason'] == '복구' and up['outages'][0]['duration_s'] >= 60
    events = [json.loads(l) for l in (tmp_path / 'service' / 'outages.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [e['event'] for e in events] == ['down', 'up'] and events[0]['cause'] == 'video_lost'


def test_a_logged_loss_of_the_input_is_shown_at_once_and_a_dead_process_changes_the_cause(tmp_path):
    watch, clock, state = make(tmp_path)
    write_rows(tmp_path, 's1', [beat(), status_record('no_input', 9.0)], clock.now - 1)
    first = watch.poll()
    assert first['state'] == 'down' and first['cause'] == 'video_lost'
    state['alive'] = False                                               # the run dies while it waited for the input
    second = watch.poll()
    assert second['cause'] == 'process_dead' and second['headline'] == '분석 프로그램 종료' and second['outage_id'] == first['outage_id']
    assert [r['causes'] for r in watch.listing()] == [['영상 입력 끊김', '분석 프로그램 종료']]
    events = [json.loads(l)['event'] for l in (tmp_path / 'service' / 'outages.jsonl').read_text(encoding='utf-8').splitlines()]
    assert events == ['down', 'cause']


def test_a_dead_process_is_found_even_while_the_file_is_still_fresh(tmp_path):
    watch, clock, _ = make(tmp_path, alive=False)
    write_rows(tmp_path, 's1', [beat()], clock.now - 1)
    assert watch.poll()['cause'] == 'process_dead'


def test_without_a_process_number_a_silent_file_is_the_unsure_cause(tmp_path):
    watch, clock, _ = make(tmp_path)
    write_rows(tmp_path, 's1', [{k: v for k, v in beat().items() if k != 'pid'}], clock.now - 90)
    assert watch.poll()['cause'] == 'silent'


def test_the_input_coming_back_closes_the_outage(tmp_path):
    watch, clock, _ = make(tmp_path)
    write_rows(tmp_path, 's1', [beat(), status_record('no_input', 9.0)], clock.now - 1)
    assert watch.poll()['state'] == 'down'
    clock.now += 12
    write_rows(tmp_path, 's1', [beat(), status_record('no_input', 9.0), status_record('input_back', 21.0), beat()], clock.now - 1)
    assert watch.poll()['state'] == 'ok' and watch.listing()[0]['end_reason'] == '복구'


def test_an_open_outage_keeps_its_start_after_the_server_restarts(tmp_path):
    watch, clock, _ = make(tmp_path)
    write_rows(tmp_path, 's1', [beat()], clock.now - 100)
    started = watch.poll()['since']
    clock.now += 500
    again = ServiceWatch(tmp_path, clock=clock, pid_check=lambda pid: True)
    picture = again.poll()
    assert picture['since'] == started and len(again.listing()) == 1 and picture['duration_s'] == 600.0


def test_finishing_closes_the_outage_and_stays_quiet_until_the_run_writes_again(tmp_path):
    watch, clock, state = make(tmp_path, alive=False)
    write_rows(tmp_path, 's1', [beat()], clock.now - 1)
    assert watch.poll()['state'] == 'down' and watch.ack('s1') is True
    assert watch.poll()['acked'] is True
    assert watch.finish('s1') is True and watch.finish('s1') is False
    assert watch.poll()['state'] == 'idle' and watch.listing()[0]['end_reason'] == '사람이 종료 처리'
    clock.now += 10
    state['alive'] = True
    write_rows(tmp_path, 's1', [beat()], clock.now - 1)                  # a new run in the same session
    assert watch.poll()['state'] == 'ok'


def test_an_old_run_is_not_an_alarm(tmp_path):
    watch, clock, _ = make(tmp_path)
    write_rows(tmp_path, 's1', [beat()], clock.now - 5 * 3600)
    assert watch.poll()['state'] == 'idle' and watch.listing() == []


def test_the_rating_sessions_are_not_watched(tmp_path):
    watch, clock, _ = make(tmp_path)
    write_rows(tmp_path, 'pc', [{'time': 1.0, 'kind': 'person_check', 'title': 'x', 'text': 'y'}], clock.now - 500)
    assert watch.poll()['state'] == 'idle'


def test_the_heartbeat_row_carries_the_process_number_and_the_clock_time():
    row = heartbeat_record(1.0, {})
    assert row['pid'] == os.getpid() and abs(row['wall'] - time.time()) < 5 and row['kind'] == 'heartbeat'


def test_pid_alive_sees_a_running_and_a_finished_process():
    assert pid_alive(os.getpid()) is True and pid_alive(None) is None
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        assert pid_alive(child.pid) is True
    finally:
        child.kill()
        child.wait()
    assert pid_alive(child.pid) is False


def test_length_text_is_in_words():
    assert length_text(5) == '5초' and length_text(125) == '2분 5초' and length_text(3700) == '1시간 1분'
