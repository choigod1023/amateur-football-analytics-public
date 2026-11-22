import cv2
import numpy as np
import pytest
from app.guarded_team import classify_guarded
from app.main import validate_config


def _bgr(hsv):
    return tuple(map(int, cv2.cvtColor(np.uint8([[hsv]]), cv2.COLOR_HSV2BGR)[0, 0]))


def test_guarded_classifier_uses_distinct_foreground_and_can_abstain():
    refs = {'home': [0, 0, 150], 'away': [110, 210, 75]}
    frame = np.full((100, 120, 3), _bgr([60, 200, 100]), dtype=np.uint8)
    frame[10:50, 40:80] = _bgr(refs['away'])
    assert classify_guarded(frame, (40, 10, 80, 90), refs) == 'away'
    frame[10:50, 40:80] = _bgr(refs['home'])
    assert classify_guarded(frame, (40, 10, 80, 90), refs) == 'home'
    frame[:] = _bgr(refs['home'])
    assert classify_guarded(frame, (40, 10, 80, 90), refs) == 'unknown'
    frame[:] = (5, 5, 5)
    assert classify_guarded(frame, (40, 10, 80, 90), refs) == 'unknown'
    assert classify_guarded(frame, (40, 10, 80, 90), {}) == 'unknown'
    assert classify_guarded(frame, (40, 10, 80, 90), {'home':[0,0,150], 'away':[0,0,180]}) == 'unknown'


def test_opt_in_config_validation():
    validate_config({'team_classifier':'guarded_palette'})
    validate_config({'team_classifier':'median'})
    with pytest.raises(ValueError):
        validate_config({'team_classifier':'bad'})


def test_guarded_abstains_without_visible_background_or_with_clipped_box():
    refs = {'home': [0, 0, 150], 'away': [110, 210, 75]}
    shirt = _bgr(refs['away'])
    frame = np.zeros((100, 120, 3), dtype=np.uint8)
    frame[10:50, 40:80] = shirt
    # Pitch is almost black: the shirt is not proven distinct from background.
    assert classify_guarded(frame, (40, 10, 80, 90), refs) == 'unknown'
    frame[:] = _bgr([60, 200, 100])
    frame[10:50, 40:80] = shirt
    assert classify_guarded(frame, (40, 10, 80, 90), refs) == 'away'
    assert classify_guarded(frame, (-10, 10, 80, 90), refs) == 'unknown'
    assert classify_guarded(frame, (40, 10, 130, 90), refs) == 'unknown'
    assert classify_guarded(frame, (0, 0, 120, 100), refs) == 'unknown'
