"""Live picture of the incoming stream for the review server (read only, nothing is stored).

/live            page that shows the picture alone (for the people who only watch)
/live-video.mjpg motion JPEG made by ONE ffmpeg from the stream MediaMTX holds on the same computer (rtsp://127.0.0.1:18554/match)
                 that is shared by every viewer (the first viewer starts it, it stops 15 s after the last viewer left)
/live-hls/<file> HLS playlist and pieces of the same stream, passed on unchanged from MediaMTX (127.0.0.1 only, see HLS_URL); web/live-hls.js
                 uses it when the phone can play HLS (itself, or through hls.js from /vendor/hls.min.js) and falls back to /live-video.mjpg when it cannot
The bench screen (/bench) shows the same picture in a panel. When there is no stream the picture request ends and the page asks again every 3 seconds.
"""
import glob
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

RTSP_URL = os.environ.get('LIVE_VIDEO_URL', 'rtsp://127.0.0.1:18554/match')
HLS_URL = os.environ.get('LIVE_HLS_URL', 'http://127.0.0.1:18888/match')   # MediaMTX HLS output, bound to 127.0.0.1 (app/srt_path_ingest.py)
HLS_TIMEOUT = 2.0                               # seconds; no answer from MediaMTX in that time -> 502 and the page uses the JPEG picture
HLS_NAME = re.compile(r'[A-Za-z0-9_.-]+')
HLS_QUERY = re.compile(r'[A-Za-z0-9_.=&%-]{0,200}')      # MediaMTX asks for ?session=<id> and ?cookieCheck=1
HLS_TYPES = {'.m3u8': 'application/vnd.apple.mpegurl', '.mp4': 'video/mp4', '.m4s': 'video/iso.segment', '.ts': 'video/mp2t'}
MAX_VIEWERS = 20
WIDTH = 960
FPS = 8
IDLE_STOP = 15.0        # seconds without a viewer after which ffmpeg is stopped
STALL_END = 5.0         # seconds without a new picture after which a viewer's request ends (the page asks again)


def _ffmpeg():
    found = os.environ.get('LIVE_VIDEO_FFMPEG') or shutil.which('ffmpeg')
    if found:
        return found
    root = Path(__file__).resolve().parents[3]
    candidates = glob.glob(str(root / 'work' / 'ffmpeg-local' / '*' / 'bin' / 'ffmpeg.exe'))
    return candidates[0] if candidates else None


class Hub:
    """One ffmpeg for all viewers; keeps the newest JPEG."""

    def __init__(self):
        self.cond = threading.Condition()
        self.frame = None
        self.number = 0
        self.viewers = 0
        self.thread = None
        self.last_viewer = time.time()

    def join(self):
        with self.cond:
            if self.viewers >= MAX_VIEWERS:
                return False
            self.viewers += 1
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
            return True

    def leave(self):
        with self.cond:
            self.viewers = max(0, self.viewers - 1)
            self.last_viewer = time.time()

    def _run(self):
        ffmpeg = _ffmpeg()
        while ffmpeg:
            command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-rtsp_transport', 'tcp', '-i', RTSP_URL, '-an',
                       '-vf', f'fps={FPS},scale={WIDTH}:-2', '-q:v', '6', '-f', 'image2pipe', '-c:v', 'mjpeg', 'pipe:1']
            try:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError:
                return
            watchdog = threading.Thread(target=self._watch, args=(process,), daemon=True)
            watchdog.start()
            buffer = b''
            try:
                while True:
                    data = process.stdout.read(65536)
                    if not data:
                        break
                    buffer += data
                    while True:
                        start = buffer.find(b'\xff\xd8')
                        end = buffer.find(b'\xff\xd9', start + 2) if start >= 0 else -1
                        if start < 0 or end < 0:
                            break
                        picture, buffer = buffer[start:end + 2], buffer[end + 2:]
                        with self.cond:
                            self.frame, self.number = picture, self.number + 1
                            self.cond.notify_all()
            finally:
                process.kill()
                process.wait()
            with self.cond:
                self.frame = None
                if self.viewers == 0 and time.time() - self.last_viewer > IDLE_STOP:
                    return
            time.sleep(2)           # the stream is not there (yet): ask again

    def _watch(self, process):
        while process.poll() is None:
            time.sleep(2)
            with self.cond:
                if self.viewers == 0 and time.time() - self.last_viewer > IDLE_STOP:
                    process.kill()
                    return

    def pictures(self):
        last = 0
        waited = time.time()
        try:
            while True:
                with self.cond:
                    self.cond.wait_for(lambda: self.number != last and self.frame is not None, timeout=1.0)
                    picture, number = self.frame, self.number
                if picture is None or number == last:
                    if time.time() - waited > STALL_END:
                        return
                    continue
                last, waited = number, time.time()
                yield b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(picture)).encode() + b'\r\n\r\n' + picture + b'\r\n'
        finally:
            self.leave()


def install(app, web_root):
    root = Path(web_root).resolve()
    hub = Hub()

    @app.get('/live')
    def live_page():
        path = root / 'live.html'
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    def asset(url, name, media_type):
        def serve():
            path = root / name
            if not path.is_file():
                raise HTTPException(404)
            return FileResponse(path, media_type=media_type)
        app.get(url)(serve)

    asset('/live-video.css', 'live-video.css', 'text/css')
    asset('/live-video-view.js', 'live-video-view.js', 'application/javascript')
    asset('/live-hls.js', 'live-hls.js', 'application/javascript')
    asset('/vendor/hls.min.js', 'vendor/hls.min.js', 'application/javascript')     # hls.js 1.6.5 (web/vendor/README.md); live-hls.js loads it only when the browser cannot play HLS itself

    @app.get('/live-hls/{name}')
    def live_hls(name: str, request: Request):
        suffix = os.path.splitext(name)[1].lower()
        if not HLS_NAME.fullmatch(name) or '..' in name or name.startswith('.') or suffix not in HLS_TYPES:
            raise HTTPException(404)
        query = request.url.query
        if not HLS_QUERY.fullmatch(query):
            raise HTTPException(404)
        headers = {'Range': request.headers['range']} if 'range' in request.headers else {}
        url = f'{HLS_URL}/{name}' + ('?' + query if query else '')
        try:
            upstream = httpx.get(url, headers=headers, timeout=HLS_TIMEOUT, trust_env=False, follow_redirects=False)
            if upstream.status_code == 302 and upstream.headers.get('location', '').startswith(f'/match/{name}?'):
                # MediaMTX's cookie check on the first playlist: it only wants '?cookieCheck=1' back; our own request keeps no cookie
                again = upstream.headers['location'].split('?', 1)[1]
                if HLS_QUERY.fullmatch(again):
                    upstream = httpx.get(f'{HLS_URL}/{name}?{again}', headers=headers, timeout=HLS_TIMEOUT, trust_env=False, follow_redirects=False)
        except httpx.HTTPError:
            raise HTTPException(502, 'stream server did not answer')
        if upstream.status_code == 404:
            raise HTTPException(404)
        if upstream.status_code not in (200, 206):
            raise HTTPException(502, 'stream server answered ' + str(upstream.status_code))
        answer = {key: upstream.headers[key] for key in ('content-range', 'accept-ranges') if key in upstream.headers}
        answer['Cache-Control'] = 'no-store'
        return Response(upstream.content, status_code=upstream.status_code, media_type=HLS_TYPES[suffix], headers=answer)

    @app.get('/live-video.mjpg')
    def live_video():
        if not _ffmpeg():
            raise HTTPException(503, 'ffmpeg not found')
        if not hub.join():
            raise HTTPException(503, 'too many viewers')
        return StreamingResponse(hub.pictures(), media_type='multipart/x-mixed-replace;boundary=frame', headers={'Cache-Control': 'no-store'})
