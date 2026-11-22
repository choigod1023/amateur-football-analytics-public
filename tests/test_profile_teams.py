import sys
import types
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from app import team_style  # noqa: E402
from app.profile_teams import OfflineTeams, choose_mode, colour_from_features, combine, model_coverage, model_letter, profile_probabilities, shirt_accepts  # noqa: E402
from app.team_color_profile import save_profile, shirt_colour  # noqa: E402
from app.team_role_features import FEATURE_NAMES, box_features  # noqa: E402

CLASSES = ['referee', 'spectator', 'team_a', 'team_b']
OLD_LEGEND = '노랑=팀 A(밝은 옷)  하늘=팀 B(어두운 옷)'


def shirt(bgr, size=(200, 100)):
    image = np.full((size[0], size[1], 3), (40, 120, 40), np.uint8)       # grass
    image[:, 20:80] = bgr
    return image


BOX = [20, 0, 80, 100]
BLUE, ORANGE, DARK, NEON = (200, 60, 20), (20, 120, 250), (25, 25, 25), (40, 240, 220)


def profile_of(own_bgr, opponent_bgr):
    """A profile whose own team wears `own_bgr` and whose opponent wears `opponent_bgr` (colours read the way the coach's page reads them)."""
    own, opponent = shirt_colour(shirt(own_bgr), BOX), shirt_colour(shirt(opponent_bgr), BOX)
    return {'version': 1, 'created': '2026-11-18T12:00:00', 'own': {'centre': own.tolist(), 'scale': 5.0, 'people': 9},
            'opponent': {'centre': opponent.tolist(), 'scale': 5.0, 'people': 9}, 'others': [], 'separation': 3.0, 'note': '', 'source': {}}


def test_profile_decides_the_letters_whatever_the_clothes():
    teams = OfflineTeams(profile_of(BLUE, ORANGE))                      # own team in blue vests: not the dark team of the first match
    assert teams.letter_of_box(shirt(BLUE), BOX) == 'B'
    assert teams.letter_of_box(shirt(ORANGE), BOX) == 'A'
    assert teams.letter_of_box(shirt(BLUE), [20, 0, 80, 20]) is None       # too small to read: unclear, never a guess


def test_old_shirt_label_stays_without_a_profile_and_follows_the_profile_with_one():
    import cv2
    from track_review_clip import shirt_label
    assert shirt_label(cv2, np, shirt(NEON), BOX) == 'A' and shirt_label(cv2, np, shirt(DARK), BOX) == 'B' and shirt_label(cv2, np, shirt(BLUE), BOX) == 'B'     # the colour rule of the first match
    teams = OfflineTeams(profile_of(NEON, BLUE))                          # now the neon team is the own team
    assert shirt_label(cv2, np, shirt(NEON), BOX, teams) == 'B' and shirt_label(cv2, np, shirt(BLUE), BOX, teams) == 'A'


def test_own_letter_can_be_chosen():
    teams = OfflineTeams(profile_of(BLUE, ORANGE), own_letter='A')
    assert teams.letter_of_box(shirt(BLUE), BOX) == 'A' and teams.letter_of_box(shirt(ORANGE), BOX) == 'B'


def test_colour_from_features_follows_the_mean_colour_of_the_patch():
    image = shirt(BLUE, (160, 80))
    point = colour_from_features(box_features(image, [0.2, 0.0, 0.8, 1.0]))
    reference = shirt_colour(image, [20, 0, 80, 160])
    assert np.linalg.norm(point[1:] - reference[1:]) < 12                     # near the picture colour, not equal (mean instead of median, grass not removed)
    assert colour_from_features(np.zeros(len(FEATURE_NAMES), np.float32)) is None


def test_model_letter_and_combine():
    assert model_letter([0.0, 0.1, 0.1, 0.8], CLASSES) == 'B'
    assert model_letter([0.0, 0.1, 0.45, 0.45], CLASSES) is None                # not clearly ahead
    assert model_letter([0.0, 0.9, 0.05, 0.05], CLASSES) is None                # spectator is not a team letter
    assert combine('A', 'B', 'profile') == 'A' and combine(None, 'B', 'profile') is None
    assert combine('A', 'B', 'fallback') == 'A' and combine(None, 'B', 'fallback') == 'B'
    assert combine('A', 'B', 'model') == 'B' and combine('A', None, 'model') == 'A'
    with pytest.raises(ValueError):
        combine('A', 'B', 'x')


def test_profile_probabilities_move_only_the_team_mass():
    teams = OfflineTeams(profile_of(BLUE, ORANGE))
    blue_features = box_features(shirt(BLUE, (160, 80)), [0.2, 0.0, 0.8, 1.0])
    # a player the model calls team_a with 0.8: the blue profile says own team (B), so the whole team mass goes to team_b
    p = profile_probabilities(teams, blue_features, CLASSES, [0.0, 0.1, 0.8, 0.1], 'profile')
    assert p[3] == pytest.approx(0.9) and p[2] == 0.0 and p[1] == pytest.approx(0.1)
    # a spectator (little team mass) stays a spectator: the profile does not turn people of the stands into players
    q = profile_probabilities(teams, blue_features, CLASSES, [0.05, 0.9, 0.03, 0.02], 'profile')
    assert int(np.argmax(q)) == 1 and q.sum() == pytest.approx(1.0)
    # no readable colour: the team mass is split evenly, so the track label stays unclear in profile mode
    r = profile_probabilities(teams, np.zeros(len(FEATURE_NAMES), np.float32), CLASSES, [0.0, 0.1, 0.8, 0.1], 'profile')
    assert r[2] == pytest.approx(r[3])
    # fallback: no readable colour, so the model decides (team_a was clearly ahead)
    s = profile_probabilities(teams, np.zeros(len(FEATURE_NAMES), np.float32), CLASSES, [0.0, 0.1, 0.8, 0.1], 'fallback')
    assert s[2] == pytest.approx(0.9) and s[3] == 0.0


def test_model_coverage_and_mode_choice():
    letters = ['A', 'B'] * 20
    assert choose_mode(letters, letters) == 'model'                            # the model gives a team on every box
    assert choose_mode(letters, [None, 'A'] * 20) == 'fallback'                # on half of them only: the model does not know these clothes
    assert choose_mode(letters[:10], letters[:10]) == 'fallback'               # too few boxes to trust the model
    assert model_coverage([None, None], ['A', 'B']) == (0, 0.0)


def test_shirt_accepts_the_followed_player():
    assert shirt_accepts([None, None, None], 'B') is True                      # nothing decided: no reason to refuse
    assert shirt_accepts(['B', 'B', 'A'], 'B') is True and shirt_accepts(['A', 'A', 'B'], 'B') is False


def test_team_style_texts_and_colours():
    style = team_style.style_from_profile(profile_of(BLUE, ORANGE))
    assert style['names']['B'].startswith('우리 팀(') and style['names']['A'].startswith('상대 팀(') and style['names']['B'].endswith('옷)')
    assert style['legend'].count('=') == 2 and '우리 팀' in style['legend'] and '상대 팀' in style['legend']
    assert team_style.team_name(None, 'B') == '팀 B(어두운 옷)' and team_style.team_name(None, 'A') == '팀 A(밝은 옷)'
    assert team_style.legend_text(None) == OLD_LEGEND
    assert all(max(c) >= team_style.MIN_VALUE - 2 for c in style['bgr'].values())      # drawn colours are visible on a dark board
    colours = {'A': (1, 2, 3), 'B': (4, 5, 6)}
    alias = colours
    team_style.apply_colours(style, colours)
    assert alias['B'] == style['bgr']['B'] and alias['A'] == style['bgr']['A']
    team_style.apply_colours(None, colours)
    assert alias['B'] == style['bgr']['B']                                    # without a style nothing changes


def test_short_name_follows_the_current_style():
    team_style.set_current(None)
    assert team_style.short_name('A') == '팀 A' and team_style.short_name('X') == '팀 X'
    team_style.set_current(team_style.style_from_profile(profile_of(BLUE, ORANGE)))
    try:
        assert team_style.short_name('B') == '우리 팀' and team_style.short_name('A') == '상대 팀'
    finally:
        team_style.set_current(None)


def test_cli_setup_without_profile_changes_nothing_and_missing_file_stops(tmp_path):
    import report_video
    import review_shots
    import tactical_draw
    import team_profile_cli
    before = dict(review_shots.TEAM_BGR)
    assert team_profile_cli.setup(types.SimpleNamespace(team_profile=None)) == (None, None)
    assert review_shots.TEAM_BGR == before
    with pytest.raises(SystemExit):
        team_profile_cli.setup(types.SimpleNamespace(team_profile=str(tmp_path / 'missing.json')))
    path = tmp_path / 'team_profile.json'
    save_profile(path, profile_of(BLUE, ORANGE))
    try:
        style, teams = team_profile_cli.setup(types.SimpleNamespace(team_profile=str(path)))
        assert style['names']['B'].startswith('우리 팀') and teams.letter_of_box(shirt(BLUE), BOX) == 'B'
        assert review_shots.TEAM_BGR['B'] == style['bgr']['B']
        assert '우리 팀' in report_video.LEGEND['text'] and '우리 팀' in tactical_draw.LEGEND['text']
    finally:
        review_shots.TEAM_BGR.update(before)
        team_style.set_current(None)
        report_video.LEGEND['text'] = OLD_LEGEND
        tactical_draw.LEGEND['text'] = OLD_LEGEND


def test_standard_palette_when_lifted_colours_look_alike():
    style = team_style.style_from_profile(profile_of(BLUE, ORANGE))
    assert style['palette'] == 'profile'
    similar = team_style.style_from_profile(profile_of(DARK, (150, 190, 150)))        # a dark team and a pale one: after lifting to the same brightness they look alike
    assert similar['palette'] == 'standard' and similar['bgr']['B'] == team_style.STANDARD_BGR['own'] and similar['bgr']['A'] == team_style.STANDARD_BGR['opponent']
    assert similar['legend'] == '노랑=상대 팀  하늘=우리 팀'
