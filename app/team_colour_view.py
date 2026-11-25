"""The two shirt colours of the current match for the pictures (bench mini-map, bench alert picture, half-time mini-maps).

Read only: <store>/service/team_profile.json, the profile the coach's team choice writes (app/team_color_profile.py, /setup and /team-select).
A new match moves that file to the archive, so the file is the colour of the match being set up or played.
The stored colour points are [0.6 * L, a, b] in the Lab space of OpenCV (L 0..100, a and b about -128..127, D65); they are turned into sRGB hex for the page.
When there is no profile or it cannot be read: ours = the green of the design (web/site.css --c-pitch), theirs = a light grey (never red: our own shirts may be red).
The pages tell the two teams apart by the ring as well (ours thick and white, theirs thin and dark), so two close shirt colours still read.
"""
from pathlib import Path

from app.team_color_profile import LIGHT_WEIGHT, colour_name, load_profile

DEFAULT_OURS, DEFAULT_THEIRS = '#40d678', '#c8cec9'


def lab_to_hex(centre):
    """[0.6 L, a, b] -> '#rrggbb' (sRGB, D65), clipped to the displayable range."""
    lightness, a, b = float(centre[0]) / LIGHT_WEIGHT, float(centre[1]), float(centre[2])
    fy = (lightness + 16.0) / 116.0
    fx, fz = fy + a / 500.0, fy - b / 200.0

    def inverse(t):
        return t ** 3 if t ** 3 > 0.008856 else (t - 16.0 / 116.0) / 7.787
    x, y, z = 0.95047 * inverse(fx), 1.0 * inverse(fy), 1.08883 * inverse(fz)
    linear = (3.2406 * x - 1.5372 * y - 0.4986 * z, -0.9689 * x + 1.8758 * y + 0.0415 * z, 0.0557 * x - 0.2040 * y + 1.0570 * z)

    def gamma(c):
        c = min(1.0, max(0.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return '#' + ''.join('%02x' % round(255 * gamma(c)) for c in linear)


def team_colours(directory):
    """{'ours': '#rrggbb', 'theirs': '#rrggbb', 'ours_name', 'theirs_name', 'source': 'profile' | 'default'}."""
    try:
        profile = load_profile(Path(directory) / 'service' / 'team_profile.json')
    except ValueError:
        profile = None
    if not profile:
        return {'ours': DEFAULT_OURS, 'theirs': DEFAULT_THEIRS, 'ours_name': '', 'theirs_name': '', 'source': 'default'}
    own, other = profile['own']['centre'], profile['opponent']['centre']
    return {'ours': lab_to_hex(own), 'theirs': lab_to_hex(other), 'ours_name': colour_name(own), 'theirs_name': colour_name(other), 'source': 'profile'}
