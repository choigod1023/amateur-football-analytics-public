"""The web side of the team choice (app/team_color_profile.py), added to the review server by one call: install(app, directory, web_root).

Page: /team-select (web/team_select.html and web/team_select.js). The pictures and colour groups come from scripts/team_select_prepare.py (<store>/service/team_select/);
the choice is written to <store>/service/team_profile.json, which scripts/run_live_feedback.py reads with --team-profile.
Writes are small and about the service only: the coach's choice and its removal. They never touch labels or ratings. The server middleware already refuses a POST with a foreign origin.
"""
import json
import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from app.team_color_profile import colour_name, load_profile, make_profile, save_profile

PAGES = {'/team-select': 'team_select.html', '/team-select.js': 'team_select.js', '/team-names.js': 'team_names.js'}
PICTURE = re.compile(r'^g[01]_[0-9]\.jpg$')


class Choice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    group: int
    confirmed: bool = False
    created: str = ''                     # the 'created' time of the candidates the coach looked at; a newer set of pictures refuses the choice


def sentence(group, colour_text):
    """The line the coach confirms once more: which picture side and which colour."""
    return f'우리 팀은 사진 {"왼쪽" if group == 0 else "오른쪽"} {colour_text} 옷 팀입니다. 맞습니까?'


def install(app, directory, web_root):
    folder = Path(directory) / 'service'
    candidates_path = folder / 'team_select' / 'candidates.json'
    profile_path = folder / 'team_profile.json'
    root = Path(web_root).resolve()

    def candidates():
        if not candidates_path.is_file():
            return None
        try:
            return json.loads(candidates_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def summary():
        try:
            profile = load_profile(profile_path)
        except ValueError as error:
            return {'error': str(error)}
        if profile is None:
            return None
        return {'created': profile['created'], 'own_colour': colour_name(profile['own']['centre']), 'opponent_colour': colour_name(profile['opponent']['centre']),
                'own_people': profile['own'].get('people'), 'opponent_people': profile['opponent'].get('people'), 'note': profile.get('note', '')}

    def page(name):
        def serve():
            path = root / name
            if not path.is_file():
                raise HTTPException(404)
            return FileResponse(path)
        return serve
    for route, name in PAGES.items():
        app.get(route)(page(name))

    @app.get('/api/v1/team-select')
    def team_select_state():
        record = candidates()
        shown = None
        if record:
            shown = {k: record.get(k) for k in ('created', 'source', 'start', 'seconds', 'people_read', 'ok', 'weak', 'reason', 'separation', 'groups', 'others_people')}
            for group in shown['groups'] or []:
                group['urls'] = [f'/team-select-files/{name}' for name in group['images']]
        return {'candidates': shown, 'profile': summary()}

    @app.get('/team-select-files/{name}')
    def team_select_file(name: str):
        path = folder / 'team_select' / name
        if not PICTURE.match(name) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type='image/jpeg')

    @app.post('/api/v1/team-select/choose')
    def team_select_choose(data: Choice):
        record = candidates()
        if not record or not record.get('ok') or len(record.get('groups') or []) < 2:
            raise HTTPException(409, '팀 색 사진이 아직 없습니다. 경기 시작 후 사진을 먼저 만들어 주세요.')
        if data.group not in (0, 1):
            raise HTTPException(400, 'Bad group')
        if data.created and data.created != record.get('created'):
            raise HTTPException(409, '그 사이에 새 사진이 만들어졌습니다. 화면을 새로 열어 다시 골라 주세요.')
        text = sentence(data.group, record['groups'][data.group]['colour_text'])
        if not data.confirmed:
            return {'saved': False, 'sentence': text}
        profile = make_profile(record['split'], data.group, note=text.replace(' 맞습니까?', ''),
                               source={'candidates_created': record.get('created'), 'video': record.get('source'), 'start': record.get('start'), 'seconds': record.get('seconds')})
        save_profile(profile_path, profile)
        return {'saved': True, 'sentence': text, 'profile': summary()}

    @app.post('/api/v1/team-select/clear')
    def team_select_clear():
        existed = profile_path.is_file()
        if existed:
            profile_path.unlink()
        return {'cleared': existed}
