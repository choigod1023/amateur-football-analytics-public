"""Standalone, explicitly public, unauthenticated review of one copied dataset.

This service is separate from live analysis and recording. Public HTTP permits
any visitor to view and change these review labels; use only when explicitly
requested. Point it at a dedicated directory, not an active service's store.
"""
import json
import os
import re
from pathlib import Path
from typing import Optional
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.ball_review import BallReview
from app.event_review import EventReview
from app.alert_review import AlertReview
from app.bench_view import BenchView
from app.service_routes import install as install_service_watch
from app.team_select_routes import install as install_team_select
from app.live_video_routes import install as install_live_video
from app.shot_routes import install as install_shots
from app.analyst_tags import install as install_analyst_tags
from app.difference_review import DifferenceReview
from app.player_identity import PlayerIdentity
from app.position_slots import POSITION_TEXT
from app.report_jobs import MAX_BYTES, ReportJobs, token_ok
from app.training_labels import TrainingLabels
from app.live_snapshot import LiveSnapshot, empty_analysis, unavailable_status


class Token(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    token: str = Field(pattern=r'^[0-9a-f]{32}$')


class DifferenceAnswer(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    id: str = Field(pattern=r'^d[0-9]{4,6}$')
    verdict: str = Field(max_length=20)
    note: str = Field(default='', max_length=500)


class Box(Token):
    bbox: list[float] = Field(min_length=4, max_length=4)


class Region(Token):
    polygon: list[list[float]] = Field(max_length=40)


class CalPoint(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    landmark: str = Field(pattern=r'^[a-z_]{3,24}$')
    x: float
    y: float


class CalPitch(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    length: float
    width: float
    circle_r: float
    goal_width: float
    pa_depth: float
    pa_width: float
    ga_depth: float
    ga_width: float


class Calibration(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    setting: str = Field(pattern=r'^cam[0-9]$')
    points: list[CalPoint] = Field(max_length=40)
    pitch: CalPitch
    ref_token: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')


class EventLabel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    id: str = Field(pattern=r'^(c[0-9]{3,4}|m[0-9a-f]{12})$')
    label: Literal['kickoff', 'goal', 'set_piece', 'shot', 'other', 'none', 'unsure', 'clear']
    event_time: float | None = None
    note: str = Field(default='', max_length=200)


class EventManual(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    time: float
    label: Literal['kickoff', 'goal', 'set_piece', 'shot', 'other', 'unsure']
    note: str = Field(default='', max_length=200)


class DeleteBox(Token):
    id: str = Field(pattern=r'^manual-[0-9a-f]{16}$')


class JobRef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job: str = Field(min_length=1, max_length=20)


class JobLog(JobRef):
    step: str = Field(min_length=1, max_length=10)


class BallClip(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    id: str = Field(pattern=r'^b[0-9]{2,3}$')


class BallLabel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    clip: str = Field(pattern=r'^b[0-9]{2,3}$')
    frame: str = Field(pattern=r'^f_[0-9]{3}\.jpg$')
    state: Literal['ball', 'none', 'unsure', 'clear']
    x: float | None = None
    y: float | None = None
    source: Literal['suggestion', 'tile', 'key', 'snap', 'manual'] | None = None


class BallVerify(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    clip: str = Field(pattern=r'^b[0-9]{2,3}$')
    frame: str = Field(pattern=r'^f_[0-9]{3}\.jpg$')
    verdict: Literal['ok', 'rejected', 'moved']
    x: float | None = None
    y: float | None = None


class Label(Token):
    track_id: str = Field(min_length=1, max_length=128)
    role: Literal['player', 'goalkeeper', 'referee', 'spectator', 'shadow', 'duplicate', 'unknown']
    team_group: Literal['team_a', 'team_b', 'white', 'blue', 'red', 'yellow', 'other', 'unknown']
    shirt_color: Literal['white', 'blue', 'yellow', 'red', 'other', 'unknown']
    shirt_detail: str = Field(default='', max_length=120)
    only_if_new: bool = False


class PlayerHalf(BaseModel):
    half: str = Field(default='', max_length=12)


class PlayerSet(BaseModel):
    id: str = Field(default='', max_length=20)
    team: str = Field(max_length=1)
    name: str = Field(default='', max_length=30)
    number: Optional[int] = None
    position: str = Field(default='', max_length=8)


class PlayerChain(BaseModel):
    half: str = Field(max_length=12)
    player: str = Field(max_length=20)


class PlayerReject(BaseModel):
    half: str = Field(max_length=12)
    player: str = Field(max_length=20)
    track: str = Field(max_length=20)
    rejected: bool = True


class PlayerRef(BaseModel):
    id: str = Field(max_length=20)


class PlayerAssign(BaseModel):
    half: str = Field(max_length=12)
    track: str = Field(max_length=20)
    player: str = Field(default='', max_length=20)


class PlayerLink(BaseModel):
    half: str = Field(max_length=12)
    a: str = Field(max_length=20)
    b: str = Field(max_length=20)
    relation: str = Field(default='', max_length=10)


class AlertLabel(BaseModel):
    id: str = Field(max_length=60)
    label: str = Field(default='', max_length=12)
    note: str = Field(default='', max_length=200)


def create_app(directory, origin, static_dir=None):
    parsed = urlsplit(origin)
    if parsed.scheme != 'http' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Expected an explicit HTTP origin')
    directory = Path(directory)
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError('Existing absolute dedicated directory required')
    store = TrainingLabels(directory)
    events = EventReview(directory)
    balls = BallReview(directory)
    reports = ReportJobs(directory)
    alerts = AlertReview(directory)
    bench = BenchView(directory)
    differences = DifferenceReview(directory)
    players = PlayerIdentity(directory)
    reports.recover()
    root = Path(static_dir or Path(__file__).resolve().parents[1] / 'web').resolve()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    snapshot_dir = os.environ.get('FOOTBALL_LIVE_SNAPSHOT_DIR')
    live_snapshot = LiveSnapshot(snapshot_dir) if snapshot_dir else None
    allowed_static = {'/train': 'train.html', '/training-label.js': 'training-label.js',
                      '/review-annotation.js': 'review-annotation.js', '/minimap.js': 'minimap.js',
                      '/events': 'events.html', '/events.js': 'events.js',
                      '/report': 'report.html', '/report.js': 'report.js', '/report.css': 'report.css',
                      '/alerts': 'alerts.html', '/alerts.js': 'alerts.js', '/alerts.css': 'alerts.css',
                      '/bench': 'bench.html', '/bench.js': 'bench.js', '/bench.css': 'bench.css',
                      '/review-differences': 'differences.html', '/train/reappearance': 'differences.html', '/differences.js': 'differences.js', '/differences.css': 'differences.css',
                      '/players': 'players.html', '/players.js': 'players.js',
                      '/cards': 'cards.html', '/cards.js': 'cards.js',
                      '/ball': 'ball.html', '/ball.js': 'ball.js', '/ball-verify.js': 'ball-verify.js',
                      '/style.css': 'style.css'}
    for filename in ('api-auth.js', 'freshness.js', 'teams.js', 'pitch.js',
                     'app.js', 'sequences.js', 'manual-confirmation.js',
                     'live-bookmarks.js', 'live-video.js', 'minimap-motion.js', 'match-roster.js'):
        allowed_static['/' + filename] = filename

    @app.middleware('http')
    async def restrict(request, call_next):
        if request.headers.get('host', '').lower() != parsed.netloc.lower():
            return __import__('starlette.responses', fromlist=['Response']).Response(status_code=403)
        if request.method == 'POST' and request.headers.get('origin') != origin:
            return __import__('starlette.responses', fromlist=['Response']).Response(status_code=403)
        response = await call_next(request)
        response.headers.setdefault('Cache-Control', 'no-store')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @app.get('/')
    def index():
        return FileResponse(root / 'index.html')

    @app.get('/api/v1/status')
    def live_status():
        if live_snapshot:
            value = live_snapshot.read()
            return value['status'] if value else unavailable_status()
        # This process serves review data, not an active live-analysis worker.
        return {'status': 'error', 'source': None, 'fps': None, 'latency_ms': None,
                'message': '라이브 분석 서버가 연결되지 않았습니다. 현재 검토 서버만 실행 중입니다.'}

    @app.get('/api/v1/analysis')
    def live_analysis():
        value = live_snapshot.read() if live_snapshot else None
        return value['analysis'] if value and value['status']['status'] == 'running' else empty_analysis()

    @app.get('/api/v1/frame.jpg')
    def live_frame():
        value = live_snapshot.frame() if live_snapshot else None
        if value is None:
            raise HTTPException(503, 'No fresh analysis frame')
        data, headers = value
        return Response(data, media_type='image/jpeg', headers=headers)

    @app.post('/api/v1/events/list')
    def event_list():
        return events.listing()

    @app.post('/api/v1/events/label')
    def event_label(data: EventLabel):
        try:
            return {'saved': events.set_label(data.id, data.label, data.event_time, data.note)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/events/manual')
    def event_manual(data: EventManual):
        try:
            return {'saved': events.add_manual(data.time, data.label, data.note)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/players/state')
    def player_state(data: PlayerHalf):
        halves = players.halves()
        chosen = data.half if data.half in halves else (halves[0] if halves else None)
        return {'halves': halves, 'roster': players.roster(), 'position_text': POSITION_TEXT, 'state': players.state(chosen) if chosen else None}

    @app.post('/api/v1/players/chain')
    def player_chain(data: PlayerChain):
        try:
            result = players.chain(data.half, data.player)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if result is None:
            raise HTTPException(404, 'Unknown half')
        return result

    @app.post('/api/v1/players/reject')
    def player_reject(data: PlayerReject):
        try:
            return {'rejected': players.set_reject(data.half, data.player, data.track, data.rejected)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/players/roster/set')
    def player_set(data: PlayerSet):
        try:
            return {'saved': players.set_player(data.id, data.team, data.name, data.number, data.position)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/players/roster/delete')
    def player_delete(data: PlayerRef):
        return {'deleted': players.delete_player(data.id)}

    @app.post('/api/v1/players/assign')
    def player_assign(data: PlayerAssign):
        try:
            return {'player': players.assign(data.half, data.track, data.player)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/players/link')
    def player_link(data: PlayerLink):
        try:
            return {'relation': players.link(data.half, data.a, data.b, data.relation)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/cards/list')
    def card_list():
        """The player cards made by scripts/build_player_cards.py (the folder `cards` of the store): its summary.json and when it was made."""
        summary = Path(directory) / 'cards' / 'summary.json'
        if not summary.is_file():
            return {'cards': [], 'made': None}
        return {'cards': json.loads(summary.read_text(encoding='utf-8')), 'made': summary.stat().st_mtime}

    @app.get('/card-files/{name}')
    def card_file(name: str):
        path = Path(directory) / 'cards' / name
        if not re.fullmatch(r'card_[A-Za-z0-9_-]{1,20}\.png', name) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type='image/png')

    @app.get('/player-files/{half}/{name}')
    def player_file(half: str, name: str):
        path = players.image(half, name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type='video/mp4' if path.suffix == '.mp4' else 'image/jpeg')

    @app.get('/api/v1/differences')
    def difference_list(include_answered: bool = False, scope: str | None = None):
        return differences.listing(include_answered, scope)

    @app.get('/api/v1/reappearance/decisions')
    def reappearance_decisions(source_sha256: str):
        if len(source_sha256) != 64 or any(c not in '0123456789abcdef' for c in source_sha256):
            raise HTTPException(400, 'A lowercase SHA256 video fingerprint is required')
        from app.reappearance_review import reviewed_links
        return reviewed_links(directory, source_sha256)

    @app.post('/api/v1/differences')
    def difference_answer(data: DifferenceAnswer):
        try:
            return {'saved': differences.answer(data.id, data.verdict, data.note)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get('/difference-files/{name}')
    def difference_file(name: str):
        path = differences.media(name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type={'mp4': 'video/mp4', 'jpg': 'image/jpeg', 'png': 'image/png'}[path.suffix[1:]])

    @app.post('/api/v1/alerts/list')
    def alert_list():
        return alerts.listing()

    @app.post('/api/v1/alerts/label')
    def alert_label(data: AlertLabel):
        try:
            return {'saved': alerts.set_label(data.id, data.label, data.note)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get('/api/v1/bench')
    def bench_snapshot(session: str = None):
        return bench.snapshot(session if session and len(session) <= 40 else None)

    @app.get('/alert-files/{session}/{name}')
    def alert_file(session: str, name: str):
        path = alerts.image(session, name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type='video/mp4' if path.suffix == '.mp4' else 'image/jpeg')

    @app.post('/api/v1/report/list')
    def report_list():
        return {**reports.listing(), 'upload_enabled': bool(reports.token), 'cameras': reports.cameras(), 'health': reports.health()}

    def require_token(request):
        if not token_ok(request.headers.get('x-report-token', ''), reports.token):
            raise HTTPException(403, 'Access token required (or changes are not enabled on this server)')

    @app.post('/api/v1/report/upload')
    async def report_upload(request: Request, camera: str, team: str, direction: int, end: float, start: float = 0.0, half_name: str = '', name: str = '',
                            title: str = '', goals: str = ''):
        require_token(request)
        try:
            declared = int(request.headers.get('content-length', '0'))
        except ValueError:
            declared = 0
        if declared > MAX_BYTES:
            raise HTTPException(413, 'File too large')
        try:
            job_id, target = reports.new_job({'camera': camera, 'team': team, 'direction': direction, 'start': start, 'end': end, 'half_name': half_name,
                                              'title': title, 'goals': goals}, name)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        size = 0
        try:
            with open(target, 'wb') as handle:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, 'File too large')
                    handle.write(chunk)
            if size == 0:
                raise HTTPException(422, 'Empty upload')
        except Exception as exc:
            reports.fail(job_id, '업로드가 끝나지 않았습니다.')
            raise exc
        reports.queue(job_id)
        return {'job': job_id}

    @app.post('/api/v1/report/cancel')
    def report_cancel(data: JobRef, request: Request):
        require_token(request)
        try:
            return {'done': reports.cancel(data.job)}
        except ValueError as exc:
            raise HTTPException(404, 'Unknown job') from exc

    @app.post('/api/v1/report/retry')
    def report_retry(data: JobRef, request: Request):
        require_token(request)
        try:
            return {'done': reports.retry(data.job)}
        except ValueError as exc:
            raise HTTPException(404, 'Unknown job') from exc

    @app.post('/api/v1/report/delete')
    def report_delete(data: JobRef, request: Request):
        require_token(request)
        try:
            return {'done': reports.delete(data.job)}
        except ValueError as exc:
            raise HTTPException(404, 'Unknown job') from exc

    @app.post('/api/v1/report/log')
    def report_log(data: JobLog, request: Request):
        require_token(request)
        try:
            return {'text': reports.log_tail(data.job, data.step)}
        except ValueError as exc:
            raise HTTPException(404, 'Unknown job or log') from exc

    @app.get('/report-files/{job}/{name}')
    def report_file(job: str, name: str):
        try:
            path = reports.output(job, name)
        except ValueError:
            path = None
        if path is None:
            raise HTTPException(404)
        kind = {'.mp4': 'video/mp4', '.md': 'text/plain; charset=utf-8', '.json': 'application/json'}[path.suffix]
        return FileResponse(path, media_type=kind)

    @app.post('/api/v1/ball/list')
    def ball_list():
        return balls.listing()

    @app.post('/api/v1/ball/clip')
    def ball_clip(data: BallClip):
        clip = balls.clip(data.id)
        if clip is None:
            raise HTTPException(404, 'Unknown clip')
        return clip

    @app.post('/api/v1/ball/label')
    def ball_label(data: BallLabel):
        try:
            return {'saved': balls.set_label(data.clip, data.frame, data.state, data.x, data.y, data.source)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/ball/verify')
    def ball_verify(data: BallVerify):
        try:
            return {'saved': balls.verify(data.clip, data.frame, data.verdict, data.x, data.y)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get('/ball-media/{clip}/{name}')
    def ball_media(clip: str, name: str):
        path = balls.media(clip, name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})

    @app.get('/event-media/{name}')
    def event_media(name: str):
        path = events.media(name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type='video/mp4' if name.endswith('.mp4') else 'image/jpeg',
                            headers={'Cache-Control': 'private, max-age=3600'})

    @app.get('/thumbs/{name}')
    def thumb(name: str):
        if not re.fullmatch(r'[0-9a-f]{32}\.jpg', name):
            raise HTTPException(404)
        path = store.thumbnail(name[:-4])
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})

    install_service_watch(app, directory, root)         # /watch, /halftime and their APIs (outage watch and half-time report)
    install_shots(app, directory, root)                 # /shots: a person tags what happened in the box moments of a match; xG (app/shot_routes.py)
    install_analyst_tags(app, directory, root)          # /tag: the analyst presses a button at a moment of the match; clips from the recordings (app/analyst_tags.py)
    install_live_video(app, root)                       # /live and /live-video.mjpg: the incoming stream as a picture (app/live_video_routes.py)
    install_team_select(app, directory, root)         # /team-select: the coach says once which colour group is the own team (app/team_select_routes.py)

    @app.get('/{name:path}')
    def static(name: str):
        filename = allowed_static.get('/' + name)
        path = (root / filename).resolve() if filename else None
        if path is None or path.parent != root or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.post('/api/v1/training-labels/latest')
    def latest():
        value = store.latest_pending()
        if not value:
            raise HTTPException(404, 'No saved snapshot')
        return value

    @app.post('/api/v1/training-labels/scenes')
    def scenes():
        return {'scenes': store.scene_queue()}

    @app.post('/api/v1/training-labels/pitch-regions')
    def pitch_regions():
        return {'regions': store.pitch_regions()}

    @app.post('/api/v1/training-labels/pitch-region')
    def pitch_region(data: Region):
        try:
            return {'regions': store.set_pitch_region(data.token, data.polygon)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/training-labels/calibrations')
    def calibrations():
        return {'calibrations': store.calibrations()}

    @app.post('/api/v1/training-labels/calibration')
    def calibration(data: Calibration):
        try:
            return {'calibrations': store.set_calibration(
                data.setting, [p.model_dump() for p in data.points], data.pitch.model_dump(), data.ref_token)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/training-labels/scene-labels')
    def scene_labels(data: Token):
        try:
            return {'labels': store.scene_labels(data.token)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/training-labels/delete-box')
    def delete_box(data: DeleteBox):
        try:
            return {'remaining': store.delete_manual_box(data.token, data.id)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/training-labels/restore')
    def restore(data: Token):
        try:
            return store.restore(data.token)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/training-labels/suggestions')
    def suggestions(data: Token):
        try:
            return {'suggestions': store.suggest(data.token), 'confirmed_ids': store.confirmed_ids(data.token)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/training-labels/manual-box')
    def add_box(data: Box):
        try:
            return {'token': data.token, 'person': store.add_manual_box(data.token, data.bbox)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/training-labels')
    def save(data: Label):
        if data.role in ('referee', 'spectator', 'shadow', 'duplicate', 'unknown') and data.team_group != 'unknown':
            raise HTTPException(422, 'This role must use an unknown team')
        try:
            ident = store.save(data.token, data.track_id, data.role, data.team_group,
                               data.shirt_color, data.shirt_detail, only_if_new=data.only_if_new)
            return {'saved': True, 'id': ident}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return app


def main():
    import uvicorn
    origin = os.environ['FOOTBALL_REVIEW_ORIGIN']
    directory = os.environ['FOOTBALL_REVIEW_DIR']
    app = create_app(directory, origin)
    uvicorn.run(app, host=os.environ.get('FOOTBALL_REVIEW_BIND', '127.0.0.1'),
                port=int(os.environ.get('FOOTBALL_REVIEW_PORT', '8443')), access_log=False, proxy_headers=False)


if __name__ == '__main__':
    main()
