"""Replay of past matches (/replay): the coach or a player picks a recorded match on a phone and watches it from any moment.

Nothing is made or converted. The recorder (scripts/record_stream_loop.ps1) writes one folder per match into the recordings folder
(<name>/YYYY-MM-DD_HH-MM-SS.mp4, pieces of about 10 minutes, fragmented MP4, the stream copied as it came). This module only
  GET  /api/v1/replay                 reads the folder names and lists the matches that have pieces (name, date, length, number of pieces),
  GET  /api/v1/replay/{match}         gives the pieces of one match (offset and length on the match timeline, address) and its marks,
  GET  /replay-video/{match}/{piece}  hands a piece out as it is on disk, with Range support (206) so that the phone can jump to any moment.
The page (web/replay.html, replay.js) plays the pieces one after another and keeps one slider over the whole match.

Safety: a match name or piece name from a request is never used to build a path. It is looked up in what the folder listing found
(names that match a fixed pattern only), so "../x", absolute paths and files outside the recordings folder are 404.
The only program run is ffprobe, to read the length of a piece (no encoding); it is skipped for a piece that is still being written.

Marks (shown under the player): the analyst tags (<store>/analyst-tags/tags.jsonl, server time of the button press) and the goals of the score board
(<store>/alerts/<session>/score.jsonl, "t" = server time of the press). A mark is placed on a match only when its time lies inside a recorded piece:
position = time - start of the piece (the piece start is the time in its file name, to the second) + the offset of the piece. Nothing is guessed:
a mark that falls outside the pieces (a gap, before the recording, no recording at all) is counted as "unlinked" and not listed.
A press comes some seconds after the event, so the page jumps LEAD seconds before the mark.
Like the other review pages there is no login: whoever can open the server can watch every recorded match.
"""
import bisect
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app import analyst_tags, score_board, tag_clips

MATCH_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
PIECE = tag_clips.PIECE
LEAD = 5.0                      # seconds before a mark at which the page starts
GAP_TOLERANCE = 2.0             # seconds a mark may lie after the end of the length ffprobe gave (file name times are only whole seconds)
GROWING_SECONDS = 60.0          # a piece changed within this time is still being recorded: no ffprobe, length estimated from the file time
WINDOW = 600.0                  # marks up to this many seconds outside a match still count as "unlinked" for it
SAME_GOAL_SECONDS = 15.0        # a tag goal and a score-board goal of the same team this close are one goal
CHUNK = 256 * 1024
MAX_PIECE_LENGTH = 660.0
TEST_PREFIXES = ('test-', 'rehearsal')         # recordings made to try the system: listed apart from the real matches


def is_test(name):
    return name.lower().startswith(TEST_PREFIXES)


def date_of(name, first_start):
    """The day of a match as a date: read from the folder name (YYYYMMDD, or MMDD in the year of the first piece), else the day of the first piece."""
    year = dt.datetime.fromtimestamp(first_start).year
    for found in (re.search(r'(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)', name), re.search(r'(?<!\d)()(\d{2})(\d{2})(?!\d)', name)):
        if found:
            try:
                return dt.date(int(found.group(1)) if found.group(1) else year, int(found.group(2)), int(found.group(3)))
            except ValueError:
                continue
    return dt.datetime.fromtimestamp(first_start).date()


def label_of(name, first_start):
    """'11월 20일 경기' for a match, '11월 24일 시험' for a test recording (a name without a readable day uses the day of the first piece)."""
    day = date_of(name, first_start)
    return '%d월 %d일 %s' % (day.month, day.day, '시험' if is_test(name) else '경기')


def default_ffprobe(ffmpeg=None):
    """ffprobe next to the ffmpeg the server already uses, else the one on PATH, else None."""
    ffmpeg = ffmpeg or tag_clips.default_ffmpeg()
    beside = Path(str(ffmpeg)).with_name('ffprobe' + ('.exe' if os.name == 'nt' else ''))
    if beside.is_file():
        return str(beside)
    return shutil.which('ffprobe')


def locate(pieces, epoch, snap=False):
    """Position on the match timeline (seconds) of a wall-clock time, or None.
    pieces: [{'start', 'duration', 'offset'}] in time order. A time inside a piece (up to GAP_TOLERANCE after its end) is placed there.
    snap=True: a time in a gap or before the first piece is moved forward to the start of the next piece (used for the lead-in, never for the mark itself)."""
    if not pieces:
        return None
    starts = [p['start'] for p in pieces]
    k = bisect.bisect_right(starts, epoch) - 1
    if k < 0:
        return pieces[0]['offset'] if snap else None
    p = pieces[k]
    rel = epoch - p['start']
    if rel <= p['duration'] + GAP_TOLERANCE:
        return p['offset'] + min(rel, p['duration'])
    if snap and k + 1 < len(pieces):
        return pieces[k + 1]['offset']
    return None


def seek_for(pieces, epoch, lead=LEAD):
    """Where the page starts for a mark: `lead` seconds of wall-clock time before it (never before the start of the recording)."""
    return locate(pieces, epoch - lead, snap=True)


def clock_text(item):
    """"전반 12:34" like the tag page, or '' when the mark has no match clock."""
    if not item or item[0] is None:
        return ''
    half, since = item
    minutes, seconds = divmod(int(since), 60)
    return '%s %d:%02d' % ('전반' if half == 'h1' else '후반', minutes, seconds)


class Replay:
    def __init__(self, store, recordings=None, ffprobe=None):
        self.store = Path(store)
        self.recordings = Path(recordings) if recordings else Path(os.environ.get('FOOTBALL_RECORDINGS') or tag_clips.default_recordings())
        self.ffprobe = default_ffprobe() if ffprobe is None else (ffprobe or None)      # False: never run ffprobe
        self.lock = threading.Lock()
        self.lengths = {}                     # path -> (size, mtime_ns, seconds) of finished pieces only

    # ----- the recordings folder
    def _length(self, path, start, stat):
        """(seconds, estimated). ffprobe for a finished piece (cached), the file time for one that is still growing or cannot be read."""
        growing = time.time() - stat.st_mtime < GROWING_SECONDS
        if not growing:
            with self.lock:
                hit = self.lengths.get(path)
            if hit and hit[0] == stat.st_size and hit[1] == stat.st_mtime_ns:
                return hit[2], False
            if self.ffprobe:
                try:
                    flags = getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0)
                    out = subprocess.run([self.ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                                         capture_output=True, timeout=20, creationflags=flags, text=True).stdout.strip()
                    seconds = float(out)
                    if seconds > 0:
                        with self.lock:
                            self.lengths[path] = (stat.st_size, stat.st_mtime_ns, seconds)
                        return seconds, False
                except (OSError, ValueError, subprocess.SubprocessError):
                    pass
        return max(0.0, min(stat.st_mtime - start, MAX_PIECE_LENGTH)), True

    def scan(self, measure=True):
        """{match name: {'dir', 'pieces': [piece]}} from the folder listing, newest match first. A piece: name, path, start, size, duration, offset, estimated."""
        found = {}
        if not self.recordings.is_dir():
            return found
        try:
            folders = [p for p in self.recordings.iterdir() if p.is_dir() and MATCH_NAME.match(p.name)]
        except OSError:
            return found
        rows = []
        for folder in folders:
            try:
                files = [f for f in folder.iterdir() if PIECE.match(f.name) and f.is_file()]
            except OSError:
                continue
            for f in files:
                try:
                    stat = f.stat()
                except OSError:
                    continue
                if stat.st_size <= 0:
                    continue
                rows.append((folder, f, stat))
        with ThreadPoolExecutor(max_workers=4) as pool:
            starts = [dt.datetime.strptime(PIECE.match(f.name).group(1), '%Y-%m-%d_%H-%M-%S').timestamp() for _, f, _ in rows]
            lengths = list(pool.map(lambda args: self._length(*args) if measure else (0.0, True), [(f, s, st) for (_, f, st), s in zip(rows, starts)]))
        by_match = {}
        for (folder, f, stat), start, (seconds, estimated) in zip(rows, starts, lengths):
            by_match.setdefault(folder.name, {'dir': folder, 'pieces': []})['pieces'].append(
                {'name': f.name, 'path': f, 'start': start, 'size': stat.st_size, 'duration': round(seconds, 3), 'estimated': estimated})
        for name, match in by_match.items():
            match['pieces'].sort(key=lambda p: p['start'])
            offset = 0.0
            for p in match['pieces']:
                p['offset'] = round(offset, 3)
                offset += p['duration']
            match['duration'] = round(offset, 3)
        for name in sorted(by_match, key=lambda n: by_match[n]['pieces'][0]['start'], reverse=True):
            found[name] = by_match[name]
        return found

    # ----- marks
    def _tag_rows(self):
        path = self.store / 'analyst-tags' / 'tags.jsonl'
        lines = []
        try:
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    try:
                        lines.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            return []
        tags = analyst_tags.fold(lines)
        clocks = analyst_tags.clock(tags)
        return [{'id': 'tag-' + tid, 'kind': t['kind'], 'label': analyst_tags.KINDS.get(t['kind'], t['kind']), 'note': t.get('note', ''),
                 'epoch': float(t['epoch']), 'clock': clock_text(clocks[tid]), 'source': 'tag'} for tid, t in tags.items()
                if isinstance(t.get('epoch'), (int, float))]

    def _goal_rows(self):
        paths = []
        alerts = self.store / 'alerts'
        for pattern in ('*/score.jsonl', '_archive*/*/score.jsonl'):
            paths += sorted(alerts.glob(pattern))
        paths += sorted((self.store / 'alerts-archive').glob('*/score.jsonl'))
        rows = []
        for path in paths:
            try:
                goals = score_board.confirmed_goals(path)
            except Exception:                                   # a damaged score file must not take the page down
                continue
            for g in goals:
                if isinstance(g.get('t'), (int, float)) and g.get('team') in ('ours', 'opp'):
                    rows.append({'id': 'goal-%s-%s' % (path.parent.name, g['id']), 'kind': 'goal_' + ('ours' if g['team'] == 'ours' else 'theirs'),
                                 'label': '우리 골' if g['team'] == 'ours' else '상대 골', 'note': '', 'epoch': float(g['t']), 'clock': '', 'source': 'score'})
        return rows

    def marks(self):
        """All marks of the store, one list, time order. A score-board goal that the tag page pressed together with a tag goal is listed once (the tag, it has the match clock)."""
        tags = self._tag_rows()
        goals = self._goal_rows()
        tag_goals = [(t['kind'], t['epoch']) for t in tags if t['kind'] in ('goal_ours', 'goal_theirs')]
        goals = [g for g in goals if not any(k == g['kind'] and abs(e - g['epoch']) <= SAME_GOAL_SECONDS for k, e in tag_goals)]
        return sorted(tags + goals, key=lambda m: m['epoch'])

    def detail(self, name, match):
        pieces = match['pieces']
        first, last = pieces[0]['start'], pieces[-1]['start'] + pieces[-1]['duration']
        placed, unlinked = [], 0
        for m in self.marks():
            if not (first - WINDOW <= m['epoch'] <= last + WINDOW):
                continue
            position = locate(pieces, m['epoch'])
            if position is None:
                unlinked += 1
                continue
            placed.append({**m, 'time': time.strftime('%H:%M:%S', time.localtime(m['epoch'])), 'position': round(position, 2),
                           'seek': round(seek_for(pieces, m['epoch']), 2)})
        return {'name': name, 'label': label_of(name, first), 'date': time.strftime('%Y-%m-%d', time.localtime(first)), 'start': first, 'duration': match['duration'], 'lead': LEAD,
                'pieces': [{'name': p['name'], 'url': '/replay-video/%s/%s' % (name, p['name']), 'start': p['start'], 'offset': p['offset'],
                            'duration': p['duration'], 'size': p['size'], 'estimated': p['estimated']} for p in pieces],
                'marks': placed, 'unlinked': unlinked}


def parse_range(header, size):
    """Range header -> (first, last) inclusive; None when there is no usable single range (the whole file is sent); ValueError when it cannot be satisfied."""
    m = re.fullmatch(r'bytes=(\d*)-(\d*)', (header or '').strip())
    if not m or (m.group(1) == '' and m.group(2) == ''):
        return None
    if m.group(1) == '':                                  # the last N bytes
        count = int(m.group(2))
        if count == 0:
            raise ValueError('empty')
        return max(0, size - count), size - 1
    first = int(m.group(1))
    last = int(m.group(2)) if m.group(2) else size - 1
    if first >= size or (m.group(2) and last < first):
        if m.group(2) and last < first:
            return None                                   # a reversed range is invalid syntax: ignored
        raise ValueError('beyond the end')
    return first, min(last, size - 1)


def install(app, directory, web_root, recordings=None, ffprobe=None):
    replay = Replay(directory, recordings, ffprobe)
    web = Path(web_root).resolve()

    def page(url, name, media_type=None):
        def serve():
            path = web / name
            if not path.is_file():
                raise HTTPException(404)
            return FileResponse(path, media_type=media_type, headers={'Cache-Control': 'no-store'}) if media_type else FileResponse(path, headers={'Cache-Control': 'no-store'})
        app.get(url)(serve)

    page('/replay', 'replay.html')
    page('/replay.js', 'replay.js', 'application/javascript')
    page('/replay-time.js', 'replay-time.js', 'application/javascript')
    page('/replay.css', 'replay.css', 'text/css')

    @app.get('/api/v1/replay')
    def replay_list():
        matches = replay.scan()
        rows = [{'name': n, 'date': time.strftime('%Y-%m-%d', time.localtime(m['pieces'][0]['start'])), 'label': label_of(n, m['pieces'][0]['start']), 'test': is_test(n),
                 'start': m['pieces'][0]['start'], 'duration': m['duration'], 'pieces': len(m['pieces']), 'size': sum(p['size'] for p in m['pieces'])} for n, m in matches.items()]
        same = [r['label'] for r in rows]
        for row in rows:                                               # two matches on one day: the time of day tells them apart
            if same.count(row['label']) > 1:
                row['label'] += ' ' + time.strftime('%H:%M', time.localtime(row['start']))
        return {'matches': [r for r in rows if not r['test']], 'tests': [r for r in rows if r['test']]}

    @app.get('/api/v1/replay/{match}')
    def replay_match(match: str):
        found = replay.scan().get(match) if MATCH_NAME.match(match) else None
        if not found:
            raise HTTPException(404)
        return replay.detail(match, found)

    def video(match, piece, request, head):
        found = replay.scan(measure=False).get(match) if MATCH_NAME.match(match) else None
        entry = next((p for p in found['pieces'] if p['name'] == piece), None) if found else None
        if entry is None:
            raise HTTPException(404)
        path = entry['path']
        try:
            if path.resolve().parent != found['dir'].resolve():          # a link that leads out of the match folder
                raise HTTPException(404)
            size = path.stat().st_size
        except OSError:
            raise HTTPException(404)
        headers = {'Accept-Ranges': 'bytes', 'Cache-Control': 'private, max-age=60', 'Content-Type': 'video/mp4'}
        try:
            span = parse_range(request.headers.get('range'), size)
        except ValueError:
            return Response(status_code=416, headers={'Content-Range': 'bytes */%d' % size, **headers})
        first, last = span if span else (0, size - 1)
        length = last - first + 1
        headers['Content-Length'] = str(length)
        if span:
            headers['Content-Range'] = 'bytes %d-%d/%d' % (first, last, size)
        status = 206 if span else 200
        if head:
            return Response(status_code=status, headers=headers)

        def body():
            with open(path, 'rb') as handle:
                handle.seek(first)
                left = length
                while left > 0:
                    chunk = handle.read(min(CHUNK, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                    yield chunk
        return StreamingResponse(body(), status_code=status, headers=headers)

    @app.get('/replay-video/{match}/{piece}')
    def replay_video(match: str, piece: str, request: Request):
        return video(match, piece, request, False)

    @app.head('/replay-video/{match}/{piece}')
    def replay_video_head(match: str, piece: str, request: Request):
        return video(match, piece, request, True)
