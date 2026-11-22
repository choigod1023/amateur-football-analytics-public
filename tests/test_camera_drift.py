import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.camera_drift import CameraDriftTracker
from app.pitch_map import feet_to_metres

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


def textured(seed=3, width=1920, height=1080):
    """A picture with plenty of corner-like detail on the lower half, like a pitch with lines, people and the grass pattern."""
    rng = np.random.default_rng(seed)
    image = cv2.GaussianBlur(rng.integers(0, 255, (height, width, 3), dtype=np.uint8), (0, 0), 2.5)
    for _ in range(400):
        centre = (int(rng.integers(0, width)), int(rng.integers(height // 2, height)))
        cv2.circle(image, centre, int(rng.integers(3, 14)), tuple(int(v) for v in rng.integers(0, 255, 3)), -1)
    for _ in range(120):
        a = (int(rng.integers(0, width)), int(rng.integers(height // 2, height)))
        b = (int(rng.integers(0, width)), int(rng.integers(height // 2, height)))
        cv2.line(image, a, b, (240, 240, 240), 2)
    return image


def shifted(image, dx, dy):
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(image, matrix, (image.shape[1], image.shape[0]), borderMode=cv2.BORDER_REPLICATE)


@pytest.fixture(scope='module')
def reference():
    return textured()


def test_a_small_move_like_the_second_half_of_cam3_is_measured_to_about_a_pixel(reference):
    tracker = CameraDriftTracker(reference, pitch_top=0.5)
    assert tracker.usable
    assert tracker.update(shifted(reference, -7, 7), 0.0) == 'ok'
    assert tracker.shift[0] == pytest.approx(-7, abs=1.5) and tracker.shift[1] == pytest.approx(7, abs=1.5)


def test_the_shift_has_the_sign_that_feet_to_metres_expects(reference):
    """A player who stands at the same place of the pitch must get the same metres whether the camera sat still or drifted."""
    fitted = {'H': np.array([[89.0, 0, -44.5], [0, 62.0, -31.0], [0, 0, 1.0]]), 'pitch': {'length': 89.0, 'width': 62.0}}
    box = (900, 700, 940, 800)
    still = feet_to_metres(fitted, box, 1920, 1080)
    tracker = CameraDriftTracker(reference, pitch_top=0.5)
    assert tracker.update(shifted(reference, 12, -9), 0.0) == 'ok'
    drifted_box = (box[0] + 12, box[1] - 9, box[2] + 12, box[3] - 9)
    assert feet_to_metres(fitted, drifted_box, 1920, 1080) != pytest.approx(still, abs=0.1)         # without the shift the player is misplaced
    compensated = feet_to_metres(fitted, drifted_box, 1920, 1080, shift=tracker.shift)
    assert compensated == pytest.approx(still, abs=0.25)


def test_a_move_that_is_too_large_is_given_up(reference):
    tracker = CameraDriftTracker(reference, pitch_top=0.5, max_shift=24.0)
    assert tracker.update(shifted(reference, 60, 0), 0.0) == 'moved'


def test_a_picture_that_cannot_be_matched_is_unknown_and_never_ok(reference):
    tracker = CameraDriftTracker(reference, pitch_top=0.5)
    blank = np.full_like(reference, 90)
    assert tracker.update(blank, 0.0) == 'unknown'
    assert tracker.update(reference[:540], 1.0) == 'unknown'                                       # another size than the photo


def test_a_short_gap_keeps_the_last_shift_and_a_long_gap_does_not(reference):
    tracker = CameraDriftTracker(reference, pitch_top=0.5, period=1.0, hold_seconds=10.0)
    assert tracker.update(shifted(reference, 5, 5), 0.0) == 'ok'
    first = tracker.shift
    blank = np.full_like(reference, 90)
    assert tracker.update(blank, 5.0) == 'ok' and tracker.shift == first                            # 5 s without evidence: the last shift
    assert tracker.update(blank, 30.0) == 'unknown'                                                # 30 s: do not place players


def test_it_measures_only_every_period_and_a_bad_fit_among_good_ones_does_not_move_the_median(reference):
    tracker = CameraDriftTracker(reference, pitch_top=0.5, period=5.0)
    tracker.update(shifted(reference, 4, 4), 0.0)
    state, shift = tracker.state, tracker.shift
    assert tracker.update(shifted(reference, 18, 18), 2.0) == state and tracker.shift == shift        # 2 s later: no new measurement
    for k, t in enumerate((5.0, 10.0, 15.0)):
        tracker.update(shifted(reference, 4, 4), t)
    tracker.update(shifted(reference, 20, 20), 20.0)                                                # one odd measurement
    assert tracker.shift[0] == pytest.approx(4, abs=1.5)


def test_the_tracker_reports_unusable_when_the_photo_has_no_detail():
    tracker = CameraDriftTracker(np.full((1080, 1920, 3), 120, np.uint8), pitch_top=0.5)
    assert not tracker.usable
    assert tracker.update(np.full((1080, 1920, 3), 120, np.uint8), 0.0) == 'unknown'
