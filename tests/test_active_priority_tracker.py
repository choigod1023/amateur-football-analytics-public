import numpy as np
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
from app.active_priority_tracker import ActivePriorityBYTETracker
from app.tracking_motion import tracker_config


def update(tracker, boxes):
    return tracker.update(Boxes(np.asarray(boxes, dtype=np.float32).reshape(-1,6), (100,100)))


def box(x):
    return [x,10,x+20,60,.9,0]


def test_lost_neighbour_does_not_steal_continuously_observed_player():
    outputs=[]
    for cls in (BYTETracker, ActivePriorityBYTETracker):
        tracker=cls(tracker_config(5))
        outputs.append([update(tracker, rows)[:,4].tolist() for rows in
                        ([box(10),box(18)],[box(12)],[box(17)])])
    assert outputs[0] == [[1.,2.],[1.],[2.]]
    assert outputs[1] == [[1.,2.],[1.],[1.]]


def test_lost_player_can_still_return_when_active_has_no_match():
    tracker=ActivePriorityBYTETracker(tracker_config(5))
    first=update(tracker,[box(10),box(70)])
    update(tracker,[box(10)])
    returned=update(tracker,[box(10),box(70)])
    assert returned[:,4].tolist() == first[:,4].tolist()
    assert len(set(returned[:,7])) == 2


def test_empty_frame_does_not_create_or_publish_predicted_players():
    tracker=ActivePriorityBYTETracker(tracker_config(5))
    assert len(update(tracker,[])) == 0
    assert len(update(tracker,[box(10)])) == 0
    assert len(update(tracker,[box(10)])) == 1
    assert len(update(tracker,[])) == 0
