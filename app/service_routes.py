"""The web side of the outage watch (app/service_watch.py) and the half-time report (app/halftime_report.py), added to the review server by one call: install(app, directory, web_root).

Pages: /watch (state of the live run, the log of stops, the half-time button), /halftime?session=NAME (the report), and web/watch-banner.js, a red band with sound that the bench screen
also loads. Reading is free; the writes are small and about the service only: silence or close a stop, press the half-time button, confirm or refuse a suggested end.
They never touch the ratings of people (alerts/labels) or any label store. The server middleware already refuses a POST with a foreign origin.
"""
from pathlib import Path
from typing import Literal, Optional

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.bench_view import SESSION
from app.coach_feedback import CoachFeedback, latest_positions
from app.halftime_report import HalftimeService
from app.halftime_rich import RichReports, current_session
from app.service_watch import ServiceWatch
from app.team_colour_view import team_colours

PAGES = {'/bench-extra.js': 'bench-extra.js', '/watch': 'watch.html', '/watch.js': 'watch.js', '/watch.css': 'watch.css', '/watch-banner.js': 'watch-banner.js', '/halftime': 'halftime.html', '/halftime.js': 'halftime.js', '/halftime.css': 'halftime.css'}


class SessionRef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session: str = Field(min_length=1, max_length=40)


class HalftimeStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session: Optional[str] = Field(default=None, max_length=40)
    end_s: Optional[float] = Field(default=None, ge=0, le=1e7)
    confirmed: bool = False                    # True: the end_s was suggested by the service and a person confirmed it


class HalftimeDismiss(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session: str = Field(min_length=1, max_length=40)
    end_s: Optional[float] = Field(default=None, ge=0, le=1e7)


class CoachAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session: str = Field(min_length=1, max_length=40)
    number: int = Field(ge=0, le=99999)
    label: Literal['ok', 'wrong']


def install(app, directory, web_root, start_thread=True):
    watch = ServiceWatch(directory)
    halftime = HalftimeService(directory, watch)
    root = Path(web_root).resolve()

    def page(name):
        def serve():
            path = root / name
            if not path.is_file():
                raise HTTPException(404)
            return FileResponse(path)
        return serve
    for route, name in PAGES.items():
        app.get(route)(page(name))

    @app.get('/api/v1/service')
    def service_state():
        return watch.poll()

    @app.post('/api/v1/service/ack')
    def service_ack(data: SessionRef):
        return {'acked': watch.ack(data.session)}

    @app.post('/api/v1/service/finish')
    def service_finish(data: SessionRef):
        return {'finished': watch.finish(data.session)}

    @app.get('/api/v1/halftime')
    def halftime_state(session: str = None):
        if session is not None and not SESSION.match(session):
            raise HTTPException(400, 'Bad session')
        return halftime.status(session)

    @app.get('/api/v1/halftime/report')
    def halftime_report(session: str, half: int = 1):
        if not SESSION.match(session) or half not in (1, 2):
            raise HTTPException(400, 'Bad session')
        if half == 2:
            try:
                return halftime.second_half_report(session)
            except (ValueError, OSError) as exc:
                raise HTTPException(404, str(exc)) from exc
        report = halftime.report(session)
        if report is None:
            raise HTTPException(404, 'No report yet')
        return report

    rich = RichReports(directory)

    @app.get('/api/v1/halftime/rich')
    def halftime_rich(session: str = None, half: int = 1):
        """The picture-first report (app/halftime_rich.py), made again from the records on request. While the half runs it is the report "so far"; after "전반 끝" it stops at the
        end the button saved. Never writes anything."""
        if session is not None and not SESSION.match(session):
            raise HTTPException(400, 'Bad session')
        if half not in (1, 2):
            raise HTTPException(400, 'Bad half')
        session = session or current_session(directory)        # no session in the address: the match of /setup (the rule of the score board)
        if not session:
            return {'session': None, 'state': 'empty', 'status_text': '진행 중인 라이브 실행이 없습니다.', 'blocks': {}}
        state = halftime._state(session) or {}
        end_s = state.get('end_s') if half == 1 and state.get('status') == 'ready' else None
        try:
            report = rich.get(session, half, end_s, final=end_s is not None)
        except (OSError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {**report, 'team_colours': team_colours(directory)} if isinstance(report, dict) else report     # the shirt colours of the match for the dots (2026-11-25)

    @app.post('/api/v1/halftime/start')
    def halftime_start(data: HalftimeStart):
        session = data.session or (halftime.status().get('session'))
        if not session or not SESSION.match(session):
            raise HTTPException(409, '진행 중인 라이브 실행이 없습니다.')
        try:
            return halftime.start(session, data.end_s, 'confirmed' if data.confirmed else 'coach')
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/halftime/confirm')
    def halftime_confirm(data: SessionRef):
        return {'confirmed': halftime.confirm(data.session)}

    @app.post('/api/v1/halftime/second-half')
    def halftime_second_half(data: SessionRef):
        if not SESSION.match(data.session):
            raise HTTPException(400, 'Bad session')
        try:
            direction = halftime.switch_second_half(data.session)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {'switched': direction is not None, 'direction': direction}

    @app.post('/api/v1/halftime/colour-checked')
    def halftime_colour_checked(data: SessionRef):
        return {'checked': halftime.colour_checked(data.session)}

    @app.post('/api/v1/halftime/dismiss')
    def halftime_dismiss(data: HalftimeDismiss):
        if not SESSION.match(data.session):
            raise HTTPException(400, 'Bad session')
        return {'dismissed': halftime.dismiss(data.session, data.end_s)}

    feedback = CoachFeedback(directory)

    @app.get('/api/v1/bench/minimap')
    def bench_minimap(session: str = None):
        session = session or halftime._live_session()
        if not session or not SESSION.match(session):
            return {'session': None}
        path = halftime.positions_file(session)
        colours = team_colours(directory)       # the shirt colours of the match for the dots of the map and of the alert picture (2026-11-25)
        if path is None:
            return {'session': session, 'positions': None, 'team_colours': colours}
        state = halftime.accumulator(session).state
        current = state['halves'].get(str(state['half'])) if state.get('header') else None
        return {'session': session, 'positions': latest_positions(path, current['direction'] if current else None), 'team_colours': colours}

    @app.get('/api/v1/bench/feedback')
    def bench_feedback_state(session: str, numbers: str = ''):
        if not SESSION.match(session):
            raise HTTPException(400, 'Bad session')
        wanted = [int(n) for n in numbers.split(',')[:12] if n.strip().isdigit()]
        return {'session': session, 'labels': {str(k): v for k, v in feedback.state(session, wanted).items()}, 'summary': feedback.summary(session)}

    @app.post('/api/v1/bench/feedback')
    def bench_feedback_set(data: CoachAnswer):
        try:
            record = feedback.set(data.session, data.number, data.label)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {'saved': True, 'label': record['label'], 'origin': record['origin'], 'user': feedback.user_label(data.session, data.number)}

    if start_thread:
        watch.start()
        halftime.start_thread()
    return watch, halftime
