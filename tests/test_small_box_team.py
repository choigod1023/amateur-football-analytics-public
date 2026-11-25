import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.small_box_team import SmallBoxTeam  # noqa: E402
from app.team_color_profile import ProfileClassifier, shirt_colour  # noqa: E402

# the 11-20 profile (work/match-1120/reanalysis/team_profile.json): own = light green bib, opponent = red bib
PROFILE = {'version': 1, 'own': {'centre': [36.294, -15.0, 25.5], 'scale': 12.37}, 'opponent': {'centre': [35.294, 25.25, 9.0], 'scale': 9.01}, 'others': []}


def bgr_of(point):
    """BGR pixel of a colour point [0.6 L, a, b]."""
    lab = np.array([[[point[0] / 0.6 * 255 / 100, point[1] + 128, point[2] + 128]]], np.float32).clip(0, 255).astype(np.uint8)
    return tuple(int(v) for v in cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)[0, 0])


def frame_with(bgr, height=25):
    image = np.full((60, 40, 3), (110, 120, 100), np.uint8)     # pale worn grass, not removed by the grass rule
    image[5:5 + height, 12:24] = bgr
    return image, [12, 5, 24, 5 + height]


GREEN_BIB, DARK_COAT, RED_BIB = (36.0, -15.0, 25.0), (21.0, -9.0, 9.0), (35.0, 25.0, 9.0)


def test_only_20_to_29_px_boxes_apply_unless_all_sizes():
    small, every = SmallBoxTeam(PROFILE, 0.4), SmallBoxTeam(PROFILE, 0.4, all_sizes=True)
    assert small.applies([0, 0, 10, 20]) and small.applies([0, 0, 10, 29.9]) and SmallBoxTeam.in_small_range([0, 0, 10, 25])
    assert not small.applies([0, 0, 10, 19.9]) and not small.applies([0, 0, 10, 30])
    assert every.applies([0, 0, 10, 20]) and every.applies([0, 0, 10, 80]) and not every.applies([0, 0, 10, 19.9])


def test_threshold_must_be_positive():
    with pytest.raises(ValueError):
        SmallBoxTeam(PROFILE, 0.0)


def test_green_bib_is_own_red_bib_is_opponent():
    small = SmallBoxTeam(PROFILE, 0.4)
    image, box = frame_with(bgr_of(GREEN_BIB))
    side, score = small.read(image, box)
    assert side == 'own' and score > 0.9
    image, box = frame_with(bgr_of(RED_BIB))
    assert small.classify_box(image, box) == 'opponent'


def test_dark_coat_is_not_own_although_its_mean_colour_is():
    image, box = frame_with(bgr_of(DARK_COAT))
    assert ProfileClassifier(PROFILE).classify(shirt_colour(image, box, min_height=0)) == 'own'     # the old reading (mean colour) lets it in
    side, score = SmallBoxTeam(PROFILE, 0.4).read(image, box)
    assert side is None and score < 0.1


def test_a_bib_on_part_of_the_torso_counts_by_its_share():
    image, box = frame_with(bgr_of(DARK_COAT))
    image[5:13, 12:24] = bgr_of(GREEN_BIB)                       # upper third light green, the rest dark
    small = SmallBoxTeam(PROFILE, 0.4)
    _, score = small.read(image, box)
    assert 0.1 < score < 0.9
    assert small.read(image, box)[0] == ('own' if score >= 0.4 else None)


def test_team_votes_use_the_small_reader_only_when_on():
    pytest.importorskip('ultralytics')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from run_live_feedback import TeamVotes
    green, box = frame_with(bgr_of(GREEN_BIB))
    coat, _ = frame_with(bgr_of(DARK_COAT))
    off = TeamVotes(profile=PROFILE, own_letter='B', other_letter='A')
    assert off.small is None and off.letter_of(green, box) is None                 # 25 px: not read, as before
    on = TeamVotes(profile=PROFILE, own_letter='B', other_letter='A', small_box_team=0.4)
    assert on.letter_of(green, box) == 'B' and on.letter_of(coat, box) is None
    big, bigbox = frame_with(bgr_of(DARK_COAT), height=40)
    assert on.letter_of(big, bigbox) == off.letter_of(big, bigbox) == 'B'          # 30 px and more: the mean-colour reading is unchanged


def test_all_sizes_reads_large_boxes_by_pixels():
    pytest.importorskip('ultralytics')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from run_live_feedback import TeamVotes
    coat, box = frame_with(bgr_of(DARK_COAT), height=40)
    green, _ = frame_with(bgr_of(GREEN_BIB), height=40)
    small_only = TeamVotes(profile=PROFILE, own_letter='B', other_letter='A', small_box_team=0.4)
    every = TeamVotes(profile=PROFILE, own_letter='B', other_letter='A', small_box_team=0.4, small_box_all=True)
    assert small_only.letter_of(coat, box) == 'B'                  # 40 px: mean colour (unchanged without all sizes)
    assert every.letter_of(coat, box) is None and every.letter_of(green, box) == 'B'
    small_coat, small_box = frame_with(bgr_of(DARK_COAT), height=15)
    assert every.letter_of(small_coat, small_box) is None          # under 20 px: still unread
