"""Shared set-up of the team colour profile for the report and video scripts (--team-profile).

add_argument(parser) adds the option; setup(args) returns (style, teams): style = names and drawing colours (app/team_style.py), teams = box classifier of the profile (app/profile_teams.py).
Both are None without --team-profile, and every script then keeps its old text and colours. With a profile the drawing colours of the modules review_shots, report_video,
tactical_draw and render_tracking_check are overwritten in place (they are plain dicts shared by every importer).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def add_argument(parser):
    parser.add_argument('--team-profile', help='team_profile.json of /team-select: texts say 우리 팀 / 상대 팀 with the colours the coach chose and the pictures use these colours; without it the old texts of the first match (team B dark, team A bright) stay')


def setup(args, own_letter='B'):
    path = getattr(args, 'team_profile', None)
    if not path:
        return None, None
    from app.profile_teams import OfflineTeams
    from app.team_color_profile import load_profile
    from app.team_style import apply_colours, set_current, style_from_profile
    profile = load_profile(path)
    if profile is None:
        raise SystemExit(f'Team profile file not found: {path}. Choose the own team on /team-select first, or run without --team-profile.')
    style = style_from_profile(profile, own_letter)
    set_current(style)
    maps = []
    for module_name, attribute in (('review_shots', 'TEAM_BGR'), ('report_video', 'TEAM_COLOURS'), ('tactical_draw', 'COLOURS'), ('render_tracking_check', 'COLOURS')):
        try:
            module = __import__(module_name)
        except ImportError:
            continue
        maps.append(getattr(module, attribute))
    apply_colours(style, *maps)
    for module_name in ('report_video', 'tactical_draw'):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, 'LEGEND'):
            module.LEGEND['text'] = style['legend']
    return style, OfflineTeams(profile, own_letter)
