"""The shot tagging page (/shots): a person says what happened in the moments in which a team got players into the opponent's box, and where a shot was taken.

Moments and clips are prepared offline (scripts/make_shot_candidates.py) into <store>/shots/. Tags are written to <store>/shots/tags/<id>.json (one small file per moment, replaced as a whole).
Shots the page did not offer (for example from outside the box) are added by hand and kept as <store>/shots/tags/x-<number>.json. The xG of a tag is computed with app/xg.py (a rough model).
The page needs no login, like the other review pages, and writes only these files.
"""
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from app.xg import xg

RESULTS = ('none', 'off', 'saved', 'blocked', 'post', 'goal')
CLIP = re.compile(r'^s[0-9]{3}\.mp4$')
TAG_ID = re.compile(r'^(s[0-9]{3}|x-[0-9]{3})$')
SIDES = ('ours', 'theirs')


def _number(value, low, high):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, 'Bad number')
    if not (low <= value <= high):
        raise HTTPException(400, 'Number out of range')
    return value


def install(app, directory, web_root):
    root = Path(directory) / 'shots'
    web = Path(web_root).resolve()
    lock = threading.Lock()

    def page(url, name, media_type=None):
        def serve():
            path = web / name
            if not path.is_file():
                raise HTTPException(404)
            return FileResponse(path, media_type=media_type) if media_type else FileResponse(path)
        app.get(url)(serve)

    page('/shots', 'shots.html')
    page('/shots.js', 'shots.js', 'application/javascript')
    page('/shots.css', 'shots.css', 'text/css')

    def candidates():
        try:
            data = json.loads((root / 'candidates.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {'candidates': [], 'pitch_length': 89.0, 'pitch_width': 62.0}
        return data

    def tags():
        out = {}
        folder = root / 'tags'
        if folder.is_dir():
            for path in sorted(folder.glob('*.json')):
                try:
                    out[path.stem] = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
        return out

    def write(tag_id, record):
        folder = root / 'tags'
        folder.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=folder, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(record, handle, ensure_ascii=False)
            os.replace(temporary, folder / (tag_id + '.json'))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @app.get('/api/v1/shots')
    def shots_list():
        data = candidates()
        return {**data, 'tags': tags()}

    @app.get('/shots-clip/{name}')
    def shots_clip(name: str):
        if not CLIP.match(name):
            raise HTTPException(404)
        path = root / 'clips' / name
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type='video/mp4')

    def record(result, side, x, y, length):
        if result not in RESULTS:
            raise HTTPException(400, 'Bad result')
        if side not in SIDES:
            raise HTTPException(400, 'Bad side')
        out = {'result': result, 'side': side, 'saved': time.strftime('%Y-%m-%dT%H:%M:%S')}
        if result != 'none':
            u = _number(x, -length / 2 - 5, length / 2 + 5)
            v = _number(y, -40, 40)
            out.update({'x': round(u, 1), 'y': round(v, 1), 'xg': round(xg(u, v, attacks_right=(side == 'ours'), pitch_length=length), 3)})
        return out

    @app.post('/api/v1/shots/tag')
    async def shots_tag(request: Request):
        data = await request.json()
        tag_id = data.get('id')
        known = {c['id']: c for c in candidates()['candidates']}
        if not isinstance(tag_id, str) or tag_id not in known:
            raise HTTPException(404, 'Unknown moment')
        with lock:
            side = known[tag_id]['side'] if known[tag_id]['side'] in SIDES else data.get('side')      # a moment of unknown team (the goals of 2026-11-11): the reviewer says which team
            out = record(data.get('result'), side, data.get('x'), data.get('y'), candidates().get('pitch_length', 89.0))
            write(tag_id, out)
        return {'id': tag_id, **out}

    @app.post('/api/v1/shots/clear')
    async def shots_clear(request: Request):
        data = await request.json()
        tag_id = data.get('id')
        if not isinstance(tag_id, str) or not TAG_ID.match(tag_id):
            raise HTTPException(400, 'Bad id')
        with lock:
            try:
                (root / 'tags' / (tag_id + '.json')).unlink()
            except OSError:
                pass
        return {'cleared': tag_id}

    @app.post('/api/v1/shots/extra')
    async def shots_extra(request: Request):
        data = await request.json()
        match, half = data.get('match'), data.get('half')
        known_matches = {c['match'] for c in candidates()['candidates']}
        if match not in known_matches or half not in ('전반', '후반'):
            raise HTTPException(400, 'Bad match or half')
        minute = _number(data.get('minute'), 0, 60)
        with lock:
            folder = root / 'tags'
            number = 1 + len(list(folder.glob('x-*.json'))) if folder.is_dir() else 1
            tag_id = f'x-{number:03d}'
            out = record(data.get('result'), data.get('side'), data.get('x'), data.get('y'), candidates().get('pitch_length', 89.0))
            out.update({'match': match, 'half': half, 'minute': round(minute, 1), 'manual': True})
            write(tag_id, out)
        return {'id': tag_id, **out}
