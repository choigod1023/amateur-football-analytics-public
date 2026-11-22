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
