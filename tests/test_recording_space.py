from collections import namedtuple
import threading
import time

from app import recording_space


def test_disk_space_warning_and_read_error(monkeypatch, capsys, tmp_path):
    usage = namedtuple('Usage', 'total used free')
    monkeypatch.setattr(recording_space.shutil, 'disk_usage', lambda _: usage(100, 0, recording_space.LOW_SPACE_BYTES))
    recording_space.report_free_space(tmp_path)
    assert capsys.readouterr().err == ''
    monkeypatch.setattr(recording_space.shutil, 'disk_usage', lambda _: usage(100, 0, recording_space.LOW_SPACE_BYTES - 1))
    recording_space.report_free_space(tmp_path)
    assert 'Recording warning' in capsys.readouterr().err
    def fail(_):
        raise OSError('volume unavailable')
    monkeypatch.setattr(recording_space.shutil, 'disk_usage', fail)
    recording_space.report_free_space(tmp_path)
    assert 'cannot check free disk space' in capsys.readouterr().err


def test_monitor_checks_periodically_and_stops_without_leaking_thread(monkeypatch, tmp_path):
    calls = []
    ready = threading.Event()
    def check(directory):
        calls.append(directory)
        if len(calls) >= 2:
            ready.set()
    monkeypatch.setattr(recording_space, 'report_free_space', check)
    monkeypatch.setattr(recording_space, 'CHECK_INTERVAL_SECONDS', .01)
    with recording_space.watch_free_space(tmp_path):
        assert ready.wait(2)
    count = len(calls)
    time.sleep(.05)
    assert len(calls) == count
