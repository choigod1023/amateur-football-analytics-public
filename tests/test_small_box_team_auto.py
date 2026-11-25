"""The bib-pixel reader switches itself off when the profile's two team colours cannot be told apart by hue band (app/small_box_team.reader_decision)."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.small_box_team import MIN_CENTRE_CHROMA, MIN_HUE_GAP_DEG, hue_chroma, reader_decision  # noqa: E402
from app.team_color_profile import load_profile  # noqa: E402


def profile(own, opponent):
    return {'version': 1, 'own': {'centre': own, 'scale': 6.0}, 'opponent': {'centre': opponent, 'scale': 6.0}, 'others': []}


def polar(hue, chroma, light=30.0):
    return [light, chroma * float(np.cos(np.radians(hue))), chroma * float(np.sin(np.radians(hue)))]


def test_1120_green_vs_red_bib_is_on():
    on, message = reader_decision(profile([36.294, -15.0, 25.5], [35.294, 25.25, 9.0]))
    assert on and message.startswith('Small-box team reader ON: hue gap 100.8 deg') and '29.6/26.8' in message


def test_1111_hue_gap_4_8_degrees_is_off():
    on, message = reader_decision(profile([18.588, -6.0, 15.0], [40.353, -11.0, 22.0]))
    assert not on and 'hue gap 4.8 deg < 50' in message and 'falling back to mean-colour reader, vote switch disabled' in message


def test_1118_achromatic_own_colour_is_off_although_the_hue_gap_is_large_enough():
    on, message = reader_decision(profile([20.706, -8.0, 9.0], [31.529, -15.0, 29.0]))     # hue 131.6 vs 117.3 is a 14.3 deg gap: caught by the gap first
    assert not on
    on, message = reader_decision(profile(polar(300.0, 12.04), polar(120.0, 32.0)))         # 180 deg apart, own chroma 12.04
    assert not on and 'own colour chroma 12.0' in message and 'achromatic' in message and 'opponent colour' not in message
    on, message = reader_decision(profile(polar(300.0, 30.0), polar(120.0, 5.0)))
    assert not on and 'opponent colour chroma 5.0' in message


def test_hue_gap_wraps_around_360_degrees():
    on, message = reader_decision(profile(polar(350.0, 30.0), polar(20.0, 30.0)))          # 30 deg apart across 0/360, not 330
    assert not on and 'hue gap 30.0 deg' in message
    on, message = reader_decision(profile(polar(350.0, 30.0), polar(40.0, 30.0)))          # exactly 50 deg: bands just do not overlap
    assert on and 'hue gap 50.0 deg' in message
    assert MIN_HUE_GAP_DEG == 50.0 and abs(MIN_CENTRE_CHROMA - (12.04 * 26.81) ** 0.5) < 0.01
    assert hue_chroma([30.0, 0.0, -10.0])[0] == pytest.approx(270.0)


def test_chroma_threshold_boundary():
    assert reader_decision(profile(polar(0.0, MIN_CENTRE_CHROMA), polar(120.0, 30.0)))[0]
    assert not reader_decision(profile(polar(0.0, MIN_CENTRE_CHROMA - 0.1), polar(120.0, 30.0)))[0]


def test_missing_values_stop_at_start(tmp_path):
    for bad in ({'own': {'centre': [1, 2]}, 'opponent': {'centre': [1, 2, 3]}}, {'own': {'centre': [1, 2, 3]}}, {}):
        with pytest.raises(ValueError):
            reader_decision(bad)
    broken = tmp_path / 'p.json'
    broken.write_text('{"version": 1, "own": {"centre": [1, 2, 3]}, "opponent": {"centre": [1, 2, 3]}}', encoding='utf-8')
    with pytest.raises(ValueError):
        load_profile(broken)           # as before: a damaged profile aborts the run


def test_cli_turns_the_three_options_off_together_and_has_no_force_option():
    src = (ROOT / 'scripts' / 'run_live_feedback.py').read_text(encoding='utf-8')
    assert 'reader_decision(profile)' in src
    assert 'args.small_box_team, args.small_box_team_all, args.team_vote_switch = 0.0, False, 0' in src
    assert '--small-box-team-force' not in src and "'--force" not in src


def test_team_votes_without_the_reader_equal_a_run_without_the_options():
    pytest.importorskip('ultralytics')
    sys.path.insert(0, str(ROOT / 'scripts'))
    from run_live_feedback import TeamVotes
    p = profile([18.588, -6.0, 15.0], [40.353, -11.0, 22.0])
    assert reader_decision(p)[0] is False
    off = TeamVotes(profile=p, own_letter='B', other_letter='A', small_box_team=0.0, switch_streak=0, small_box_all=False)
    assert off.small is None and off.switch_streak == 0
