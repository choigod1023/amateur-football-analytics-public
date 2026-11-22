"""Analyst tags (/tag): the video analyst presses a button when something happens in the match; the server keeps the time.

Kickoff and final whistle of each half are tags too, so every tag gets a match clock ("전반 12:34"). At half time the analyst asks for clips:
the server cuts each tag's moment from the match recordings (app/tag_clips.py, copied, no re-encoding) and the page plays them.

Storage: <store>/analyst-tags/tags.jsonl, append only (add, delete and note edits are separate lines, folded when read), clips in <store>/analyst-tags/clips/<id>.mp4.
The server time of the button press is used, not the phone's clock. The page needs no login, like the other review pages; it writes only these files.
"""
import json
import os
import queue
import re
import secrets
import threading
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from app import tag_clips

MARKS = {'start_h1': '전반 시작', 'end_h1': '전반 종료', 'start_h2': '후반 시작', 'end_h2': '후반 종료'}
EVENTS = {
    'shot_ours': '우리 슛', 'shot_theirs': '상대 슛', 'goal_ours': '우리 골', 'goal_theirs': '상대 골',
    'corner_ours': '우리 코너킥', 'corner_theirs': '상대 코너킥',
    'line_high': '수비 줄 높음', 'pivot_up': '수미 둘 다 올라감', 'wide_empty': '측면 빔', 'second_ball': '세컨볼 빔', 'stretched': '팀 늘어짐',
    'good': '좋은 장면', 'danger': '위험 장면', 'note': '메모',
}
KINDS = {**MARKS, **EVENTS}
TAG_ID = re.compile(r'^[a-f0-9]{12}$')
DAY = re.compile(r'^\d{4}-\d{2}-\d{2}$')
NOTE_MAX = 200
PER_DAY_MAX = 3000


def day_of(epoch):
    return time.strftime('%Y-%m-%d', time.localtime(epoch))


def fold(lines):
    """Records of the file -> {id: tag} with deletes and note edits applied, in time order."""
    tags = {}
    for rec in lines:
        op, tag_id = rec.get('op'), rec.get('id')
        if op == 'add' and isinstance(tag_id, str):
            tags[tag_id] = {k: rec[k] for k in ('id', 'kind', 'note', 'epoch') if k in rec}
        elif op == 'delete':
            tags.pop(tag_id, None)
        elif op == 'note' and tag_id in tags:
            tags[tag_id]['note'] = rec.get('note', '')
    return dict(sorted(tags.items(), key=lambda kv: kv[1]['epoch']))


def clock(tags):
    """Half and seconds since that half's kickoff for every tag: {id: (half, seconds) or None}. A half runs from its start mark to its end mark (or on)."""
    marks = sorted((t['epoch'], t['kind']) for t in tags.values() if t['kind'] in MARKS)
    out = {}
    for tag_id, t in tags.items():
        half, since = None, None
        for epoch, kind in marks:
            if epoch > t['epoch']:
                break
            if kind.startswith('start_'):
                half, since = kind[-2:], epoch
            elif kind.startswith('end_') and t['epoch'] > epoch + 0.5:
                half, since = None, None                      # tags after the whistle of a half (half time) have no clock
        out[tag_id] = (half, t['epoch'] - since) if half else None
    return out


def install(app, directory, web_root, recordings=None, ffmpeg=None):
    root = Path(directory) / 'analyst-tags'
    store = root / 'tags.jsonl'
    clips = root / 'clips'
    web = Path(web_root).resolve()
    recordings = Path(recordings) if recordings else Path(os.environ.get('FOOTBALL_RECORDINGS') or tag_clips.default_recordings())
    ffmpeg = ffmpeg or tag_clips.default_ffmpeg()
    lock = threading.Lock()
    status = {}                       # id -> queued, running, done, no-recording, failed (clips of this server run)
    work = queue.Queue()

    def page(url, name, media_type=None):
        def serve():
            path = web / name
            if not path.is_file():
                raise HTTPException(404)
            return FileResponse(path, media_type=media_type, headers={'Cache-Control': 'no-store'}) if media_type else FileResponse(path, headers={'Cache-Control': 'no-store'})
        app.get(url)(serve)

    page('/tag', 'tag.html')
    page('/tag.js', 'tag.js', 'application/javascript')
    page('/tag.css', 'tag.css', 'text/css')

    def read():
        if not store.is_file():
            return {}
        lines = []
        with store.open(encoding='utf-8') as handle:
            for line in handle:
                try:
                    lines.append(json.loads(line))
                except ValueError:
                    continue                                  # a line cut by a crash is skipped
        return fold(lines)

    def append(rec):
        root.mkdir(parents=True, exist_ok=True)
        with store.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(rec, ensure_ascii=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())

    def clip_state(tag_id):
        if (clips / (tag_id + '.mp4')).is_file():
            return 'done'
        return status.get(tag_id, 'none')

    def listing(day):
        tags = {k: v for k, v in read().items() if day_of(v['epoch']) == day}
        clocks = clock(tags)
        items = []
        for tag_id, t in tags.items():
            c = clocks.get(tag_id)
            items.append({'id': tag_id, 'kind': t['kind'], 'label': KINDS.get(t['kind'], t['kind']), 'note': t.get('note', ''),
                          'time': time.strftime('%H:%M:%S', time.localtime(t['epoch'])), 'epoch': t['epoch'],
                          'half': c[0] if c else None, 'clock': (int(c[1]) if c else None),
                          'clip': None if t['kind'] in MARKS else clip_state(tag_id)})
        return items

    def worker():
        while True:
            tag_id, epoch = work.get()
            status[tag_id] = 'running'
            try:
                status[tag_id] = tag_clips.clip_for(epoch, recordings, ffmpeg, clips / (tag_id + '.mp4'))
            except Exception:                                 # never stop the worker
                status[tag_id] = 'failed'
            finally:
                work.task_done()

    threading.Thread(target=worker, name='analyst-tag-clips', daemon=True).start()

    @app.get('/api/v1/analyst-tags')
    def tags_list(day: str = ''):
        day = day if DAY.match(day or '') else day_of(time.time())
        return {'day': day, 'now': time.time(), 'kinds': EVENTS, 'marks': MARKS, 'items': listing(day)}

    @app.post('/api/v1/analyst-tags')
    async def tags_add(request: Request):
        data = await request.json()
        kind = data.get('kind')
        if kind not in KINDS:
            raise HTTPException(400, 'Unknown kind')
        note = data.get('note') or ''
        if not isinstance(note, str):
            raise HTTPException(400, 'Bad note')
        now = time.time()
        at = data.get('at')                                   # a press that could not be sent at once: the page sends the server time it estimated then
        delayed = isinstance(at, (int, float)) and now - 600 <= at <= now + 5
        epoch = float(at) if delayed else now
        with lock:
            if len([t for t in read().values() if day_of(t['epoch']) == day_of(now)]) >= PER_DAY_MAX:
                raise HTTPException(429, 'Too many tags today')
            rec = {'op': 'add', 'id': secrets.token_hex(6), 'kind': kind, 'note': note[:NOTE_MAX], 'epoch': round(epoch, 2)}
            if delayed:
                rec['sent_late'] = round(now - epoch, 1)
            append(rec)
        return {'id': rec['id'], 'kind': kind, 'label': KINDS[kind], 'time': time.strftime('%H:%M:%S', time.localtime(epoch))}

    @app.post('/api/v1/analyst-tags/delete')
    async def tags_delete(request: Request):
        tag_id = (await request.json()).get('id')
        if not isinstance(tag_id, str) or not TAG_ID.match(tag_id):
            raise HTTPException(400, 'Bad id')
        with lock:
            if tag_id not in read():
                raise HTTPException(404, 'Unknown tag')
            append({'op': 'delete', 'id': tag_id, 'epoch': round(time.time(), 2)})
        return {'deleted': tag_id}

    @app.post('/api/v1/analyst-tags/note')
    async def tags_note(request: Request):
        data = await request.json()
        tag_id, note = data.get('id'), data.get('note')
        if not isinstance(tag_id, str) or not TAG_ID.match(tag_id) or not isinstance(note, str):
            raise HTTPException(400, 'Bad id or note')
        with lock:
            if tag_id not in read():
                raise HTTPException(404, 'Unknown tag')
            append({'op': 'note', 'id': tag_id, 'note': note[:NOTE_MAX], 'epoch': round(time.time(), 2)})
        return {'id': tag_id}

    @app.post('/api/v1/analyst-tags/clips')
    async def tags_clips(request: Request):
        data = await request.json()
        day = data.get('day') if DAY.match(str(data.get('day') or '')) else day_of(time.time())
        queued = 0
        for item in listing(day):
            if item['clip'] in ('none', 'failed', 'no-recording'):
                status[item['id']] = 'queued'
                work.put((item['id'], item['epoch']))
                queued += 1
        return {'queued': queued, 'recordings': recordings.is_dir()}

    @app.get('/analyst-clip/{tag_id}.mp4')
    def tags_clip(tag_id: str):
        if not TAG_ID.match(tag_id):
            raise HTTPException(404)
        path = clips / (tag_id + '.mp4')
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type='video/mp4')
