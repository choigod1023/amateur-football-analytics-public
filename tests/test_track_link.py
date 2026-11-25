import argparse
import sys
from pathlib import Path

import numpy as np
import pytest
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import IterableSimpleNamespace, YAML
from ultralytics.utils.checks import check_yaml

from app.track_link import LinkTracker, link_enabled, mutual_nearest
from app.track_vote import TRACKER_SETTINGS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


def config():
    c = IterableSimpleNamespace(**YAML.load(check_yaml('bytetrack.yaml')))
    for key, value in TRACKER_SETTINGS.items():
        setattr(c, key, value)
    c.track_high_thresh = c.new_track_thresh = 0.12
    c.track_low_thresh = 0.06
    return c


def boxes(rows):
    return Boxes(np.array([[*r, 0.9, 0] for r in rows], np.float32).reshape(-1, 6), (1080, 1920))


def ids(out):
    return [int(r[4]) for r in out]


def run(tracker, frames, feet=None, teams=None, track_team=None):
    result = []
    for k, rows in enumerate(frames):
        if isinstance(tracker, LinkTracker):
            f = None if feet is None else feet[k]
            t = None if teams is None else teams[k]
            result.append(ids(tracker.update(boxes(rows), None, feet=f, det_teams=t, track_team=track_team)))
        else:
            result.append(ids(tracker.update(boxes(rows), None)))
    return result


# a player walks right, is missed for two frames and comes back far from where the coasted box went (no overlap)
WALK = [[[100, 500, 120, 550]], [[110, 500, 130, 550]], [[120, 500, 140, 550]], [], [], [[60, 500, 80, 550]]]
WALK_FEET = [np.array([[0.0, 0.0]]), np.array([[0.4, 0.0]]), np.array([[0.8, 0.0]]), np.zeros((0, 2)), np.zeros((0, 2)), np.array([[1.5, 0.0]])]


def test_all_off_is_plain_bytetracker():
    rng = np.random.default_rng(3)
    frames = []
    for k in range(40):
        rows = []
        for p in range(6):
            if rng.random() < 0.8:
                x = 100 + 80 * p + 6 * k + rng.normal(0, 3)
                rows.append([x, 500 + 10 * p, x + 20, 550 + 10 * p])
        frames.append(rows)
    feet = [np.array([[r[0] / 50, r[1] / 50] for r in rows]).reshape(-1, 2) for rows in frames]
    assert run(LinkTracker(config()), frames, feet) == run(BYTETracker(config()), frames)
    assert not link_enabled({}) and not link_enabled(None)


def test_pitch_link_keeps_the_number_when_the_feet_are_close():
    plain = run(LinkTracker(config()), WALK, WALK_FEET)
    joined = run(LinkTracker(config(), {'pitch_link': True}), WALK, WALK_FEET)
    assert plain[-1] == []                                   # the plain tracker breaks: a new, not yet confirmed number (not shown)
    assert joined[-1] == joined[0] == [1]


def test_revive_alone_keeps_the_number():
    tracker = LinkTracker(config(), {'revive': True})
    out = run(tracker, WALK, WALK_FEET)
    assert out[-1] == out[0]
    assert tracker.events[0]['kind'] == 'revive' and tracker.events[0]['gap_frames'] == 3


def test_gate_refuses_a_far_detection():
    far = WALK_FEET[:-1] + [np.array([[30.0, 0.0]])]            # 3 frames lost = 0.6 s: gate 1.5 + 3 * 0.6 = 3.3 m (default)
    out = run(LinkTracker(config(), {'pitch_link': True, 'revive': True}), WALK, far)
    assert out[-1] != out[0]
    edge = WALK_FEET[:-1] + [np.array([[0.8 + 3.4, 0.0]])]       # 3.4 m from the last foot: outside 3.3 m, inside with vmax 7 (5.7 m)
    assert run(LinkTracker(config(), {'pitch_link': True}), WALK, edge)[-1] != [1]
    assert run(LinkTracker(config(), {'pitch_link': True, 'vmax': 7.0}), WALK, edge)[-1] == [1]


def test_max_age_refuses_an_old_number():
    out = run(LinkTracker(config(), {'pitch_link': True, 'max_age_s': 0.4}), WALK, WALK_FEET)
    assert out[-1] != out[0]


def test_team_gate_refuses_the_other_team():
    teams = [['B'], ['B'], ['B'], [], [], ['A']]
    votes = lambda tid: 'B'
    out = run(LinkTracker(config(), {'pitch_link': True, 'team_gate': True}), WALK, WALK_FEET, teams, votes)
    assert out[-1] != out[0]
    unknown = [['B'], ['B'], ['B'], [], [], [None]]
    out = run(LinkTracker(config(), {'pitch_link': True, 'team_gate': True}), WALK, WALK_FEET, unknown, votes)
    assert out[-1] == out[0]


def test_ambiguous_revive_makes_a_new_number():
    two = [[[100, 500, 120, 550], [300, 500, 320, 550]]] * 3 + [[], [], [[200, 500, 220, 550]]]
    feet = [np.array([[0.0, 0.0], [2.0, 0.0]])] * 3 + [np.zeros((0, 2)), np.zeros((0, 2)), np.array([[1.0, 0.1]])]
    tracker = LinkTracker(config(), {'revive': True})
    run(tracker, two, feet)
    assert tracker.events == []


def test_mutual_nearest_margin():
    cost = np.array([[1.0, 3.0], [1.2, np.inf]])
    assert mutual_nearest(cost, 0.5) == []                       # column 0 has two rows 0.2 m apart
    assert mutual_nearest(np.array([[1.0, 3.0], [2.0, np.inf]]), 0.5) == [(0, 0)]


def test_decay_slows_a_lost_number():
    a, b = LinkTracker(config()), LinkTracker(config(), {'decay_half_life': 0.4})
    for t in (a, b):
        run(t, WALK[:5], WALK_FEET[:5])
    va, vb = a.lost_stracks[0].mean[4], b.lost_stracks[0].mean[4]
    assert va > 0 and 0 < vb < va


def test_bad_options_are_refused():
    with pytest.raises(ValueError):
        LinkTracker(config(), {'vmax': -1})
    with pytest.raises(ValueError):
        LinkTracker(config(), {'pitchlink': True})


def test_command_line_default_is_off():
    import run_live_feedback as live
    args = argparse.Namespace(link_pitch=False, link_revive=False, link_team_gate=False, link_decay_half_life=0.0, link_r0=1.5, link_vmax=7.0,
                              link_max_age=0.0, link_margin=0.5)
    assert not link_enabled(live.link_options(args))
    args.link_revive = True
    assert live.link_options(args)['revive'] and link_enabled(live.link_options(args))
