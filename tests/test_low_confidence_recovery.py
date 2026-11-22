import numpy as np
from app.low_confidence_recovery import select_recovery_boxes
from app.low_confidence_recovery import RecoveryDisplay


def test_display_recovery_is_one_sample_only_and_never_changes_inputs():
    recovery=RecoveryDisplay()
    point={'id':'7','team':'home','x':.5,'y':.5}
    pitch={'length':89,'width':60}
    tracked=[[10,10,30,70,7]]
    assert recovery.update(0, [], tracked, [point], lambda b:(0,0), pitch)==[]
    weak=[[11,10,31,70,.08]]
    recovered=recovery.update(.2, weak, [], [], lambda b:(.1,0), pitch)
    assert recovered[0]['id']=='7'
    assert recovered[0]['observation_kind']=='low_confidence_recovery'
    assert recovery.update(.4, weak, [], [], lambda b:(.2,0), pitch)==[]
    assert point=={'id':'7','team':'home','x':.5,'y':.5}
    assert tracked==[[10,10,30,70,7]]


def test_recovery_never_fills_rejected_existing_track_or_duplicates_neighbour():
    pitch={'length':89,'width':60};weak=[[11,10,31,70,.08]]
    for tracked, displayed in [([[11,10,31,70,7]],[]),([], [{'id':'8','team':'away','x':.5,'y':.5}])]:
        recovery=RecoveryDisplay()
        recovery.update(0,[],[[10,10,30,70,7]],[{'id':'7','team':'home','x':.5,'y':.5}],lambda b:(0,0),pitch)
        assert recovery.update(.2,weak,tracked,displayed,lambda b:(0,0),pitch)==[]


def test_recovery_requires_current_detection_camera_and_short_gap():
    pitch={'length':89,'width':60}
    for t,found,ready in [(.2,[],True),(.2,[[11,10,31,70,.08]],False),(.6,[[11,10,31,70,.08]],True)]:
        recovery=RecoveryDisplay()
        recovery.update(0,[],[[10,10,30,70,7]],[{'id':'7','team':'home','x':.5,'y':.5}],lambda b:(0,0),pitch)
        assert recovery.update(t,found,[],[],lambda b:(0,0),pitch,ready)==[]


def test_isolated_labelled_track_recovers_real_low_score_box():
    weak = [11,10,31,70,.08]
    assert select_recovery_boxes([weak], [[10,10,30,70,7]], {7}) == [weak]
    assert select_recovery_boxes([weak], [], {7}) == []
    assert select_recovery_boxes([weak], [[10,10,30,70,7]], set()) == []


def test_overlap_or_strong_detection_competition_vetoes_recovery():
    weak = [11,10,31,70,.08]
    old = [[10,10,30,70,7], [20,10,40,70,8]]
    assert select_recovery_boxes([weak], old, {7,8}) == []
    strong = [10,10,30,70,.9]
    assert select_recovery_boxes([weak,strong], old[:1], {7}) == [strong]


def test_partial_box_jump_and_duplicate_weak_candidates_are_rejected():
    old = [[10,10,30,70,7]]
    assert select_recovery_boxes([[10,10,30,42,.08]], old, {7}) == []
    weak = [11,10,31,70,.08]
    assert select_recovery_boxes([weak,weak], old, {7}) == [weak]
    assert select_recovery_boxes([[np.nan,10,30,70,.08]], old, {7}) == []


def test_actual_bytetrack_low_score_recovers_existing_but_cannot_spawn():
    from ultralytics.trackers.byte_tracker import BYTETracker
    from ultralytics.engine.results import Boxes
    from ultralytics.utils import IterableSimpleNamespace
    config = IterableSimpleNamespace(track_high_thresh=.12, new_track_thresh=.12,
        track_low_thresh=.06, track_buffer=50, match_thresh=.98, fuse_score=True)
    def boxes(rows):
        return Boxes(np.array(rows,dtype=np.float32).reshape(-1,6), (100,100))
    tracker=BYTETracker(config)
    assert len(tracker.update(boxes([[10,10,30,70,.08,0]]),None)) == 0
    tracker=BYTETracker(config)
    first=tracker.update(boxes([[10,10,30,70,.8,0]]),None)
    recovered=tracker.update(boxes([[11,10,31,70,.08,0]]),None)
    assert len(first)==len(recovered)==1
    assert first[0,4]==recovered[0,4]
