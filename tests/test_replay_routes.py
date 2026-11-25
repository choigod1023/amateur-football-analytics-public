import datetime as dt
import json
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import replay_routes
from app.replay_routes import locate, parse_range, seek_for

WEB = Path(__file__).resolve().parents[1] / 'web'


def epoch(text):
    return dt.datetime.strptime(text, '%Y-%m-%d_%H-%M-%S').timestamp()


def piece(folder, text, seconds, size=3000):
    """A fake piece: no ffprobe in these tests, so the length comes from the file time (start + seconds, long ago)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (text + '.mp4')
    path.write_bytes(bytes(i % 251 for i in range(size)))
    os.utime(path, (epoch(text) + seconds, epoch(text) + seconds))
    return path


def client(tmp_path, rec):
    app = FastAPI()
    replay_routes.install(app, tmp_path / 'store', WEB, recordings=rec, ffprobe=False)
    return TestClient(app)


def tags(tmp_path, rows):
    folder = tmp_path / 'store' / 'analyst-tags'
    folder.mkdir(parents=True)
    (folder / 'tags.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')


def test_list_is_made_from_the_folders_and_new_ones_appear_by_themselves(tmp_path):
    rec = tmp_path / 'rec'
    c = client(tmp_path, rec)
    assert c.get('/api/v1/replay').json() == {'matches': [], 'tests': []}       # no folder at all
    rec.mkdir()
    (rec / 'empty').mkdir()
    assert c.get('/api/v1/replay').json() == {'matches': [], 'tests': []}       # an empty folder is not a match
    piece(rec / 'match-a', '2026-11-18_16-00-00', 600)
    piece(rec / 'match-a', '2026-11-18_16-10-00', 300)
    piece(rec / 'match-b', '2026-11-20_19-00-00', 600)
    (rec / 'match-b' / 'record.log').write_text('x')                              # not a piece
    first = c.get('/api/v1/replay').json()['matches']
    assert [m['name'] for m in first] == ['match-b', 'match-a']                  # newest first
    a = first[1]
    assert a['date'] == '2026-11-18' and a['pieces'] == 2 and abs(a['duration'] - 900) < 1
    piece(rec / 'match-new', '2026-11-25_19-30-00', 120)                          # a new match, no code change
    assert [m['name'] for m in c.get('/api/v1/replay').json()['matches']][0] == 'match-new'


def test_range_gives_206_with_exactly_the_bytes_asked(tmp_path):
    rec = tmp_path / 'rec'
    path = piece(rec / 'm', '2026-11-18_16-00-00', 600, size=5000)
    c = client(tmp_path, rec)
    r = c.get('/replay-video/m/2026-11-18_16-00-00.mp4', headers={'Range': 'bytes=1000-1999'})
    assert r.status_code == 206 and len(r.content) == 1000 and r.content == path.read_bytes()[1000:2000]
    assert r.headers['content-range'] == 'bytes 1000-1999/5000' and r.headers['accept-ranges'] == 'bytes'
    r = c.get('/replay-video/m/2026-11-18_16-00-00.mp4', headers={'Range': 'bytes=4900-'})
    assert r.status_code == 206 and len(r.content) == 100
    r = c.get('/replay-video/m/2026-11-18_16-00-00.mp4', headers={'Range': 'bytes=-10'})
    assert r.status_code == 206 and r.content == path.read_bytes()[-10:]
    r = c.get('/replay-video/m/2026-11-18_16-00-00.mp4', headers={'Range': 'bytes=9000-9999'})
    assert r.status_code == 416 and r.headers['content-range'] == 'bytes */5000'
    r = c.get('/replay-video/m/2026-11-18_16-00-00.mp4')
    assert r.status_code == 200 and r.content == path.read_bytes() and r.headers['content-type'] == 'video/mp4'
    h = c.head('/replay-video/m/2026-11-18_16-00-00.mp4')
    assert h.status_code == 200 and h.headers['content-length'] == '5000' and h.content == b''


def test_parse_range():
    assert parse_range(None, 100) is None and parse_range('bytes=0-9', 100) == (0, 9) and parse_range('bytes=90-500', 100) == (90, 99)
    assert parse_range('bytes=5-2', 100) is None and parse_range('garbage', 100) is None and parse_range('bytes=0-1,5-6', 100) is None


def test_paths_that_leave_the_recordings_are_404(tmp_path):
    rec = tmp_path / 'rec'
    piece(rec / 'm', '2026-11-18_16-00-00', 600)
    (tmp_path / 'secret.mp4').write_bytes(b'secret')
    (rec / 'm' / 'x.mp4').write_bytes(b'x')                                       # a file that is not a piece name
    c = client(tmp_path, rec)
    for url in ['/replay-video/m/x.mp4', '/replay-video/m/../../secret.mp4', '/replay-video/../secret.mp4', '/replay-video/m/..%2F..%2Fsecret.mp4',
                '/replay-video/m/%2e%2e/%2e%2e/secret.mp4', '/replay-video/..%5C/secret.mp4', '/replay-video/C:/Windows/win.ini',
                '/replay-video/%2Fetc/passwd', '/replay-video/other/2026-11-18_16-00-00.mp4', '/api/v1/replay/..', '/api/v1/replay/nothing',
                '/api/v1/replay/..%2Frec', '/replay-video/m/2026-11-18_16-00-01.mp4']:
        assert c.get(url).status_code == 404, url
    assert c.get('/replay-video/m/2026-11-18_16-00-00.mp4').status_code == 200


def test_mark_time_becomes_a_place_in_the_video(tmp_path):
    pieces = [{'start': 1000.0, 'duration': 600.0, 'offset': 0.0}, {'start': 1700.0, 'duration': 300.0, 'offset': 600.0}]
    assert locate(pieces, 1000.0) == 0 and locate(pieces, 1250.5) == 250.5
    assert locate(pieces, 1700.0 + 10) == 610.0                    # second piece
    assert locate(pieces, 1650.0) is None and locate(pieces, 999.0) is None and locate(pieces, 2100.0) is None   # gap, before, after
    assert locate(pieces, 1650.0, snap=True) == 600.0              # the lead-in of a mark right after a gap starts the next piece
    assert seek_for(pieces, 1250.0) == 245.0 and seek_for(pieces, 1702.0) == 600.0 and seek_for(pieces, 1002.0) == 0


def test_marks_come_from_tags_and_goals_and_only_when_a_recording_covers_them(tmp_path):
    rec = tmp_path / 'rec'
    piece(rec / 'm', '2026-11-18_16-00-00', 600)
    piece(rec / 'm', '2026-11-18_16-10-00', 300)
    start = epoch('2026-11-18_16-00-00')
    tags(tmp_path, [
        {'op': 'add', 'id': 'a' * 12, 'kind': 'start_h1', 'note': '', 'epoch': start + 20},
        {'op': 'add', 'id': 'b' * 12, 'kind': 'shot_ours', 'note': '', 'epoch': start + 100},
        {'op': 'add', 'id': 'c' * 12, 'kind': 'goal_ours', 'note': '', 'epoch': start + 650},
        {'op': 'add', 'id': 'd' * 12, 'kind': 'shot_theirs', 'note': '', 'epoch': start + 5000},       # no recording then
        {'op': 'add', 'id': 'e' * 12, 'kind': 'good', 'note': '', 'epoch': start - 100},                 # before the recording, near it
    ])
    score = tmp_path / 'store' / 'alerts' / 'match-x'
    score.mkdir(parents=True)
    rows = [{'id': 0, 'kind': 'goal', 'team': 'ours', 't': start + 652}, {'id': 1, 'kind': 'goal', 'team': 'opp', 't': start + 700}]
    (score / 'score.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    c = client(tmp_path, rec)
    d = c.get('/api/v1/replay/m').json()
    by_kind = {m['kind']: m for m in d['marks']}
    assert set(by_kind) == {'start_h1', 'shot_ours', 'goal_ours', 'goal_theirs'}      # the score-board goal 2 s from the tag goal is one goal
    assert by_kind['shot_ours']['clock'] == '전반 1:20' and by_kind['shot_ours']['position'] == 100 and by_kind['shot_ours']['seek'] == 95
    assert by_kind['goal_ours']['source'] == 'tag' and by_kind['goal_theirs']['source'] == 'score' and by_kind['goal_theirs']['position'] == 700
    assert d['unlinked'] == 1 and d['pieces'][1]['offset'] == 600 and d['pieces'][1]['url'] == '/replay-video/m/2026-11-18_16-10-00.mp4'
    assert [m['kind'] for m in d['marks']] == ['start_h1', 'shot_ours', 'goal_ours', 'goal_theirs']


def test_a_match_without_marks_and_no_encoding_process(tmp_path, monkeypatch):
    rec = tmp_path / 'rec'
    piece(rec / 'm', '2026-11-18_16-00-00', 600)
    c = client(tmp_path, rec)
    d = c.get('/api/v1/replay/m').json()
    assert d['marks'] == [] and d['unlinked'] == 0

    def refuse(*a, **k):
        raise AssertionError('no process may run while a video is handed out')
    monkeypatch.setattr(subprocess, 'run', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    assert c.get('/replay-video/m/2026-11-18_16-00-00.mp4', headers={'Range': 'bytes=0-9'}).status_code == 206


def test_page_files_and_start_link():
    app = FastAPI()
    replay_routes.install(app, Path('.'), WEB, recordings=Path('nowhere'), ffprobe=False)
    c = TestClient(app)
    assert c.get('/replay').status_code == 200 and c.get('/replay.js').status_code == 200 and c.get('/replay.css').status_code == 200
    assert 'href="/replay"' in (WEB / 'start.html').read_text(encoding='utf-8')


def test_test_recordings_are_listed_apart_and_matches_are_named_by_their_day(tmp_path):
    rec = tmp_path / 'rec'
    piece(rec / 'match-20261120', '2026-11-20_19-00-00', 600)
    piece(rec / 'match-1118', '2026-11-18_16-00-00', 600)
    piece(rec / 'test-20261124', '2026-11-24_20-00-00', 120)
    piece(rec / 'rehearsal-20261124', '2026-11-24_21-00-00', 120)
    piece(rec / 'final', '2026-11-22_10-00-00', 600)                 # no day in the name: the day of the first piece
    piece(rec / 'match-99999999', '2026-11-05_10-00-00', 600)        # not a date: the day of the first piece
    c = client(tmp_path, rec)
    data = c.get('/api/v1/replay').json()
    assert [(m['name'], m['label']) for m in data['matches']] == [('final', '11월 22일 경기'), ('match-20261120', '11월 20일 경기'), ('match-1118', '11월 18일 경기'), ('match-99999999', '11월 5일 경기')]
    assert [(m['name'], m['label']) for m in data['tests']] == [('rehearsal-20261124', '11월 24일 시험 21:00'), ('test-20261124', '11월 24일 시험 20:00')]
    assert c.get('/api/v1/replay/match-1118').json()['label'] == '11월 18일 경기'
    piece(rec / 'match-20261120b', '2026-11-20_21-00-00', 300)         # a second match on the same day: the time of day tells them apart
    labels = [m['label'] for m in c.get('/api/v1/replay').json()['matches']]
    assert '11월 20일 경기 19:00' in labels and '11월 20일 경기 21:00' in labels
