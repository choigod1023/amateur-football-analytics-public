import datetime as dt
import json
import subprocess
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import analyst_tags, tag_clips

WEB = Path(__file__).resolve().parents[1] / 'web'


def client(tmp_path, recordings=None, ffmpeg='ffmpeg'):
    app = FastAPI()
    analyst_tags.install(app, tmp_path, WEB, recordings=recordings or tmp_path / 'rec', ffmpeg=ffmpeg)
    return TestClient(app)


def test_add_list_note_delete_and_page():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = client(Path(d))
        assert c.get('/tag').status_code == 200 and c.get('/tag.js').status_code == 200
        a = c.post('/api/v1/analyst-tags', json={'kind': 'shot_ours'}).json()
        b = c.post('/api/v1/analyst-tags', json={'kind': 'note', 'note': 'x' * 500}).json()
        assert c.post('/api/v1/analyst-tags', json={'kind': 'nope'}).status_code == 400
        c.post('/api/v1/analyst-tags/note', json={'id': a['id'], 'note': '수미 둘 다 올라감'})
        c.post('/api/v1/analyst-tags/delete', json={'id': b['id']})
        items = c.get('/api/v1/analyst-tags').json()['items']
        assert [i['id'] for i in items] == [a['id']] and items[0]['note'] == '수미 둘 다 올라감' and items[0]['label'] == '우리 슛'
        assert c.post('/api/v1/analyst-tags/delete', json={'id': 'zz'}).status_code == 400
        assert c.get('/analyst-clip/../x.mp4').status_code == 404


def test_late_press_keeps_the_estimated_time_only_within_ten_minutes():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = client(Path(d))
        now = time.time()
        c.post('/api/v1/analyst-tags', json={'kind': 'danger', 'at': now - 120})
        c.post('/api/v1/analyst-tags', json={'kind': 'danger', 'at': now - 3600})      # too old: server time is used
        epochs = sorted(i['epoch'] for i in c.get('/api/v1/analyst-tags').json()['items'])
        assert abs(epochs[0] - (now - 120)) < 1 and abs(epochs[1] - now) < 5


def test_clock_counts_from_the_kickoff_and_stops_at_the_whistle():
    tags = analyst_tags.fold([
        {'op': 'add', 'id': 'a', 'kind': 'start_h1', 'epoch': 1000.0},
        {'op': 'add', 'id': 'b', 'kind': 'shot_ours', 'epoch': 1754.0},
        {'op': 'add', 'id': 'c', 'kind': 'end_h1', 'epoch': 2360.0},
        {'op': 'add', 'id': 'd', 'kind': 'note', 'epoch': 2500.0},
        {'op': 'add', 'id': 'e', 'kind': 'start_h2', 'epoch': 2900.0},
        {'op': 'add', 'id': 'f', 'kind': 'corner_theirs', 'epoch': 2981.0},
    ])
    clock = analyst_tags.clock(tags)
    assert clock['b'] == ('h1', 754.0) and clock['c'] == ('h1', 1360.0) and clock['d'] is None and clock['f'] == ('h2', 81.0)


def test_spans_cover_two_pieces_and_skip_gaps():
    t0 = 1_000_000.0
    pieces = [(t0, Path('a.mp4')), (t0 + 600, Path('b.mp4')), (t0 + 2000, Path('c.mp4'))]
    assert tag_clips.spans(pieces, t0 + 590, t0 + 616) == [(Path('a.mp4'), 590, 600), (Path('b.mp4'), 0, 16)]
    assert tag_clips.spans(pieces, t0 + 1700, t0 + 1726) == []                     # recorder was down


def _ffmpeg():
    path = tag_clips.default_ffmpeg()
    try:
        subprocess.run([path, '-version'], capture_output=True, check=True)
    except (OSError, subprocess.SubprocessError):
        pytest.skip('ffmpeg not available')
    return path


def test_clip_is_cut_across_two_recording_pieces(tmp_path):
    ffmpeg = _ffmpeg()
    rec = tmp_path / 'rec' / 'match-test'
    rec.mkdir(parents=True)
    start = dt.datetime(2026, 11, 20, 15, 0, 0)
    for k in range(2):
        name = (start + dt.timedelta(seconds=30 * k)).strftime('%Y-%m-%d_%H-%M-%S') + '.mp4'
        subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=25', '-t', '30', '-g', '25', '-c:v', 'libx264', '-preset', 'ultrafast', str(rec / name)], check=True)
    tag_clips.DEFAULT_LENGTH = 30.0
    try:
        epoch = start.timestamp() + 40                                            # 20 s before is inside the first piece
        out = tmp_path / 'clip.mp4'
        assert tag_clips.clip_for(epoch, tmp_path / 'rec', ffmpeg, out) == 'done'
        probe = subprocess.run([str(Path(ffmpeg).with_name('ffprobe.exe')) if Path(ffmpeg).with_name('ffprobe.exe').is_file() else 'ffprobe',
                                '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(out)], capture_output=True, text=True)
        duration = float(json.loads(probe.stdout)['format']['duration'])
        assert 24 <= duration <= 28
        assert tag_clips.clip_for(start.timestamp() - 3600, tmp_path / 'rec', ffmpeg, tmp_path / 'none.mp4') == 'no-recording'
    finally:
        tag_clips.DEFAULT_LENGTH = 600.0


def _tags(*marks):
    return analyst_tags.fold([{'op': 'add', 'id': f'm{i}', 'kind': kind, 'epoch': epoch} for i, (kind, epoch) in enumerate(marks)])


def test_match_clock_follows_the_newest_mark():
    now = time.time()
    kickoff = now - 754.0
    # no mark: before the match
    assert analyst_tags.match_clock({}, now)['state'] == 'before'
    # the 4 marks in turn
    c = analyst_tags.match_clock(_tags(('start_h1', kickoff)), now)
    assert c['state'] == 'h1' and abs(now - c['since'] - 754.0) < 0.01 and c['marks'] == ['start_h1']
    c = analyst_tags.match_clock(_tags(('start_h1', now - 1400), ('end_h1', now - 100)), now)
    assert c['state'] == 'break' and c['since'] is None
    c = analyst_tags.match_clock(_tags(('start_h1', now - 1400), ('end_h1', now - 500), ('start_h2', now - 190)), now)
    assert c['state'] == 'h2' and abs(now - c['since'] - 190.0) < 0.01          # the second half counts from its own kickoff
    c = analyst_tags.match_clock(_tags(('start_h1', now - 3000), ('end_h1', now - 2000), ('start_h2', now - 1900), ('end_h2', now - 5)), now)
    assert c['state'] == 'over' and c['marks'] == ['start_h1', 'end_h1', 'start_h2', 'end_h2']
    # no length of a half is built in: 70 minutes of first half just keep counting
    assert analyst_tags.match_clock(_tags(('start_h1', now - 4200)), now)['state'] == 'h1'


def test_match_clock_starts_again_with_a_new_match_and_ignores_other_days():
    now = time.time()
    tags = _tags(('start_h1', now - 3000), ('end_h1', now - 2000), ('start_h2', now - 1900), ('end_h2', now - 600))
    assert analyst_tags.match_clock(tags, now, started=now - 3500)['state'] == 'over'
    c = analyst_tags.match_clock(tags, now, started=now - 300)                    # a new match was started after the marks of the first one
    assert c['state'] == 'before' and c['marks'] == []
    assert analyst_tags.match_clock(_tags(('start_h1', now - 86400 * 2)), now)['state'] == 'before'
    # the marks of the new match count again from its own kickoff
    tags = _tags(('end_h2', now - 600), ('start_h1', now - 60))
    c = analyst_tags.match_clock(tags, now, started=now - 300)
    assert c['state'] == 'h1' and abs(now - c['since'] - 60.0) < 0.01 and c['marks'] == ['start_h1']


def test_clock_route_is_the_same_for_marks_from_the_tag_page_and_from_the_bar_below(tmp_path):
    c = client(tmp_path)
    assert c.get('/match-clock.js').status_code == 200
    assert c.get('/api/v1/clock').json()['state'] == 'before'
    # 전반 시작 pressed on /tag, 전반 끝 and 후반 시작 on the bar below (the bar posts the same tags), 후반 종료 on /tag
    for kind, state in (('start_h1', 'h1'), ('end_h1', 'break'), ('start_h2', 'h2'), ('end_h2', 'over')):
        c.post('/api/v1/analyst-tags', json={'kind': kind})
        got = c.get('/api/v1/clock').json()
        assert got['state'] == state, (kind, got)
    assert got['marks'] == ['start_h1', 'end_h1', 'start_h2', 'end_h2']
    # a new match (match.json of /setup, created now) brings "경기 전" back; the old marks stay in the file
    setup = tmp_path / 'service' / 'setup'
    setup.mkdir(parents=True)
    (setup / 'match.json').write_text(json.dumps({'name': 'match-test', 'created': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() + 2))}), encoding='utf-8')
    assert c.get('/api/v1/clock').json()['state'] == 'before'
    assert len(c.get('/api/v1/analyst-tags').json()['items']) == 4
    c.post('/api/v1/analyst-tags', json={'kind': 'start_h1', 'at': time.time() + 3})
    got = c.get('/api/v1/clock').json()                                           # the first mark after the start of the new match (pressed 3 s ahead of the clock of the file) counts
    assert got['state'] == 'h1' and got['marks'] == ['start_h1']
