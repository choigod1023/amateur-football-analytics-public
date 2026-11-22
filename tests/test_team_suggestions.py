import cv2
import numpy as np
import pytest

from app.main import validate_config, summarize
from app.manual_tracks import ManualTracks
from app.team_suggestions import TeamSuggestions, shirt_histogram


def scene():
    frame = np.zeros((160, 320, 3), np.uint8)
    boxes = [(10, 10, 50, 110), (70, 10, 110, 110),
             (140, 10, 180, 110), (200, 10, 240, 110)]
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        frame[y1:y2, x1:x2] = (0, 0, 230) if i < 2 else (230, 0, 0)
    return frame, [(box, i) for i, box in enumerate(boxes)]


def test_unlabelled_groups_require_several_tracks_and_never_map_to_teams():
    frame, tracks = scene()
    estimator = TeamSuggestions(frames=2)
    assert all(x is None for x in estimator.update(frame, tracks).values())
    assert all(x is None for x in estimator.update(frame, tracks).values())
    out = estimator.update(frame, tracks)
    assert out['0'] == out['1'] and out['2'] == out['3']
    assert out['0'] != out['2'] and set(out.values()) == {0, 1}


def test_too_few_or_identical_tracks_abstain_and_new_instance_resets():
    frame, tracks = scene()
    insufficient = TeamSuggestions(frames=1)
    insufficient.update(frame, tracks[:2])
    assert all(x is None for x in insufficient.update(frame, tracks).values())
    frame[:] = (0, 0, 230)
    equal = TeamSuggestions(frames=1)
    equal.update(frame, tracks)
    assert all(x is None for x in equal.update(frame, tracks).values())
    assert shirt_histogram(frame, (0, 0, 5, 5)) is None
    assert TeamSuggestions().centres is None


def test_team_suggestions_are_optional_and_do_not_require_manual_mode():
    validate_config({'manual_player_assignments': True, 'suggest_team_clusters': True})
    validate_config({'suggest_team_clusters': True})
    with pytest.raises(ValueError): validate_config({'manual_player_assignments': True, 'suggest_team_clusters': 'true'})


def test_distant_colour_abstains_even_if_one_group_is_closer():
    estimator = TeamSuggestions()
    estimator.centres = np.eye(2, 16, dtype=np.float32)
    distant = np.zeros(16, dtype=np.float32)
    distant[2] = .9
    distant[0] = .1
    assert estimator._classify(distant) is None


def test_fit_retries_after_initial_insufficient_tracks():
    frame, tracks = scene()
    estimator = TeamSuggestions(frames=2)
    estimator.update(frame, tracks[:2])
    estimator.update(frame, tracks[:2])
    assert estimator.centres is None
    estimator.update(frame, tracks)
    estimator.update(frame, tracks)
    assert estimator.centres is not None
    assert all(group is not None for group in estimator.update(frame, tracks).values())


def test_unconfirmed_suggestion_never_becomes_a_team_or_metric():
    registry = ManualTracks()
    registry.observe(['1', '2'])
    players = []
    for tid in ('1', '2'):
        token, team, role = registry.get(tid)
        players.append({'id': tid, 'team': team, 'role': role,
                        'annotation_token': token, 'suggested_color_group': 0,
                        'x': .2, 'y': .3})
    registry.publish_snapshot(b'jpeg', players, 'frame')
    snapshot = registry.get_snapshot()
    assert [p['team'] for p in snapshot['players']] == ['unknown', 'unknown']
    metrics, feedback = summarize(players, 'home', (105, 68))
    assert metrics == {'team_width_m': None, 'team_length_m': None}
    assert feedback == []
