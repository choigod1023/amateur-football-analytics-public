"""The live run is never a hand-labelling session (label-...) or an archive (_...)."""
import json
import os

from app.bench_view import BenchView, is_live_session
from app.service_watch import ServiceWatch

ROW = {'time': 1.0, 'kind': 'run', 'polarity': 'poor', 'title': 't', 'text': 'x'}


def write(root, name, at):
    folder = root / 'alerts' / name
    folder.mkdir(parents=True)
    path = folder / 'alerts.jsonl'
    path.write_text(json.dumps(ROW) + '\n', encoding='utf-8')
    os.utime(path, (at, at))


def test_name_rule():
    assert is_live_session('1121-live')
    assert not is_live_session('label-1121-team')
    assert not is_live_session('_archive-1120')


def test_real_session_wins_over_newer_label_session(tmp_path):
    write(tmp_path, 'real-1', 1000)
    write(tmp_path, 'label-x', 2000)
    assert BenchView(tmp_path).snapshot()['session'] == 'real-1'
    found = ServiceWatch(tmp_path)._newest_live()
    assert found and found[0].name == 'real-1'


def test_only_label_sessions_is_like_an_empty_store(tmp_path):
    write(tmp_path, 'label-x', 2000)
    assert BenchView(tmp_path).snapshot()['session'] is None
    assert ServiceWatch(tmp_path)._newest_live() is None
    empty = tmp_path / 'other'
    empty.mkdir()
    assert BenchView(empty).snapshot()['session'] is None
    assert ServiceWatch(empty)._newest_live() is None


def test_archive_session_is_ignored(tmp_path):
    write(tmp_path, 'real-1', 1000)
    write(tmp_path, '_archive-1120', 3000)
    assert BenchView(tmp_path).snapshot()['session'] == 'real-1'
    assert ServiceWatch(tmp_path)._newest_live()[0].name == 'real-1'
