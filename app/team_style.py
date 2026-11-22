"""Names and drawing colours of the two teams for the reports, the review videos and the pictures, taken from the team colour profile of the match.

Why: the texts said "team B (dark clothes)" and "yellow = team A (bright clothes)" because the first match had dark against neon clothes.
With a profile (app/team_color_profile.py, chosen by the coach on /team-select) the texts say "우리 팀(파란색 옷)" and "상대 팀(...)" and the drawn dots take the colours of the profile.
Without a profile every function returns the old text and colour unchanged, so the first match renders as before.

The internal letters stay: the own team is 'B' (team_b) and the opponent is 'A' (team_a) in all tracking files, because the files, the labels of the human and the live run use these letters.
Only what a coach reads or sees changes.
"""
import numpy as np

from app.team_color_profile import LIGHT_WEIGHT, colour_name

OLD_NAMES = {'A': '팀 A(밝은 옷)', 'B': '팀 B(어두운 옷)'}
OLD_LEGEND = '노랑=팀 A(밝은 옷)  하늘=팀 B(어두운 옷)'
MIN_DISTANCE = 90            # two drawn colours closer than this (BGR distance) cannot be told apart on a picture; the standard pair is drawn instead (a dark and a pale team become equally bright after lifting)
STANDARD_BGR = {'own': (255, 198, 124), 'opponent': (74, 216, 255)}      # sky blue, yellow
MIN_VALUE = 190              # drawn colours are lifted to this brightness (0..255) so that a dark team stays visible on the dark board and on video; hue and saturation stay


def other_letter(letter):
    return 'A' if letter == 'B' else 'B'


def bgr_of(centre):
    """Display colour (B, G, R) of a profile colour point [0.6 * L, a, b]."""
    import cv2
    lab = np.array([[[min(255.0, max(0.0, float(centre[0]) / LIGHT_WEIGHT * 255.0 / 100.0)), float(centre[1]) + 128.0, float(centre[2]) + 128.0]]], np.float32)
    lab = np.clip(lab, 0, 255).astype(np.uint8)
    return tuple(int(v) for v in cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)[0, 0])


def lifted(bgr, minimum=MIN_VALUE):
    """The same colour made at least `minimum` bright (HSV value), for drawing only."""
    import cv2
    hsv = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0, 0].astype(int)
    hsv[2] = max(hsv[2], minimum)
    return tuple(int(v) for v in cv2.cvtColor(hsv.astype(np.uint8)[None, None], cv2.COLOR_HSV2BGR)[0, 0])


def style_from_profile(profile, own_letter='B'):
    """None without a profile. Otherwise {'names': {letter: text}, 'short': {letter: 우리 팀/상대 팀}, 'colour_words': {letter: word}, 'bgr': {letter: (b, g, r)}, 'legend': text}.
    The legend names the colour the coach sees on the pictures (a rough colour word) and the team."""
    if not profile:
        return None
    opponent_letter = other_letter(own_letter)
    words = {own_letter: colour_name(profile['own']['centre']), opponent_letter: colour_name(profile['opponent']['centre'])}
    short = {own_letter: '우리 팀', opponent_letter: '상대 팀'}
    names = {letter: f'{short[letter]}({words[letter]} 옷)' for letter in (own_letter, opponent_letter)}
    bgr = {own_letter: lifted(bgr_of(profile['own']['centre'])), opponent_letter: lifted(bgr_of(profile['opponent']['centre']))}
    palette = 'profile'
    if float(np.linalg.norm(np.array(bgr[own_letter], float) - np.array(bgr[opponent_letter], float))) < MIN_DISTANCE:
        bgr = {own_letter: STANDARD_BGR['own'], opponent_letter: STANDARD_BGR['opponent']}
        palette = 'standard'
        legend = f'노랑={short[opponent_letter]}  하늘={short[own_letter]}'
    else:
        legend = f'{words[opponent_letter]}={short[opponent_letter]}  {words[own_letter]}={short[own_letter]}'
    return {'names': names, 'short': short, 'colour_words': words, 'bgr': bgr, 'legend': legend, 'own_letter': own_letter, 'palette': palette}


def load_style(path, own_letter='B'):
    """The style of a team_profile.json (a missing file with a path given stops the run, the same as the live run does), or None when no path is given."""
    if not path:
        return None
    from app.team_color_profile import load_profile
    profile = load_profile(path)
    if profile is None:
        raise SystemExit(f'Team profile file not found: {path}. Choose the own team on /team-select first, or run without --team-profile.')
    return style_from_profile(profile, own_letter)


def apply_colours(style, *colour_maps):
    """Overwrite, in place, the {'A': bgr, 'B': bgr} maps of the drawing modules, so every alias of the same dict follows. No style: nothing changes."""
    if not style:
        return
    for colours in colour_maps:
        for letter, bgr in style['bgr'].items():
            colours[letter] = bgr


def team_name(style, letter):
    """Text of a team for a coach: 'old text' without a style."""
    return style['names'][letter] if style else OLD_NAMES[letter]


def legend_text(style):
    return style['legend'] if style else OLD_LEGEND


_CURRENT = {'style': None}


def set_current(style):
    """The style the running script uses; short_name() reads it so that deep helpers need no extra argument. None = old texts."""
    _CURRENT['style'] = style


def short_name(letter):
    """'팀 A' / 'The own team' words: '우리 팀' / '상대 팀' with a profile, else '팀 A' / '팀 B' as before."""
    style = _CURRENT['style']
    return style['short'].get(letter, f'팀 {letter}') if style else f'팀 {letter}'
