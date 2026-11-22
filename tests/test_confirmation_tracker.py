import numpy as np
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
from app.confirmation_tracker import ConfirmingBYTETracker, with_geometric_confirmation
from app.tracking_motion import tracker_config, xyah_tracker_class


def feed(tracker, rows):
    return tracker.update(Boxes(np.asarray(rows, dtype=np.float32).reshape(-1, 6), (200, 200)))


def test_low_confidence_repeated_player_is_confirmed_not_permanently_hidden():
    box = [10, 10, 30, 60, .2, 0]
    baseline, fixed = BYTETracker(tracker_config(5)), ConfirmingBYTETracker(tracker_config(5))
    for tracker in (baseline, fixed):
        assert len(feed(tracker, [])) == 0
        assert len(feed(tracker, [box])) == 0  # Still requires a second observation.
    assert len(feed(baseline, [box])) == 0
    assert len(feed(fixed, [box])) == 0  # Low-score fallback needs three sightings.
    result = feed(fixed, [box])
    assert len(result) == 1
    assert feed(fixed, [box])[0, 4] == result[0, 4]


def test_single_flash_and_subthreshold_detections_do_not_confirm():
    tracker = ConfirmingBYTETracker(tracker_config(5))
    for rows in ([], [[10, 10, 30, 60, .2, 0]], [],
                 [[10, 10, 30, 60, .1, 0]], [[10, 10, 30, 60, .1, 0]]):
        assert len(feed(tracker, rows)) == 0


def test_ambiguous_overlapping_people_are_not_forced_into_a_match():
    tracker = ConfirmingBYTETracker(tracker_config(5))
    feed(tracker, [])
    feed(tracker, [[10, 10, 30, 60, .2, 0], [12, 10, 32, 60, .2, 0]])
    assert len(feed(tracker, [[11, 10, 31, 60, .2, 0]])) == 0


def test_confirmed_identity_does_not_depend_on_detection_order():
    tracker = ConfirmingBYTETracker(tracker_config(5))
    boxes = [[10, 10, 30, 60, .2, 0], [110, 10, 130, 60, .2, 0]]
    feed(tracker, [])
    feed(tracker, boxes)
    assert len(feed(tracker, boxes)) == 0
    first = feed(tracker, boxes)
    second = feed(tracker, boxes[::-1])
    assert len(first) == len(second) == 2
    assert {int(r[4]): int(r[0]) for r in first} == {int(r[4]): int(r[0]) for r in second}
    assert len(set(second[:, 7])) == 2


def test_camera_composition_preserves_camera_hook_and_confirmation():
    base = xyah_tracker_class(True)
    cls = with_geometric_confirmation(base)
    assert cls._pre_first_associate is base._pre_first_associate
    tracker = cls(tracker_config(5))
    feed(tracker, [])
    box = [[10, 10, 30, 60, .2, 0]]
    feed(tracker, box)
    assert len(feed(tracker, box)) == 0
    assert len(feed(tracker, box)) == 1


def test_fast_high_confidence_confirmation_preserves_baseline():
    counts = []
    for cls in (BYTETracker, ConfirmingBYTETracker):
        tracker = cls(tracker_config(5))
        result = [len(feed(tracker, []))]
        for x in (10, 18, 26, 34):
            result.append(len(feed(tracker, [[x, 10, x+20, 60, .9, 0]])))
        counts.append(result)
    assert counts[0] == counts[1] == [0, 0, 1, 1, 1]


def test_gap_breaks_three_observation_confirmation():
    tracker = ConfirmingBYTETracker(tracker_config(5))
    box = [[10, 10, 30, 60, .2, 0]]
    for rows in ([], box, box, [], box, box):
        assert len(feed(tracker, rows)) == 0
