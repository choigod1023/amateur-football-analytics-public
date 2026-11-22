import numpy as np
import pytest
from app.observation_boxes import current_detection_boxes


def track(idx=0,tid=7):
    return [0,0,100,300,tid,.9,0,idx]


def test_exact_current_match_replaces_only_external_box_and_keeps_id():
    source=np.array([track()]);original=source.copy()
    detections=np.array([[10,20,25,60,.8,0]])
    rows,diag=current_detection_boxes(source,detections)
    np.testing.assert_array_equal(source,original)
    np.testing.assert_array_equal(rows[0,:4],detections[0,:4])
    np.testing.assert_array_equal(rows[0,4:],source[0,4:])
    assert diag[0]['accepted']


@pytest.mark.parametrize('idx',[-1,1,.5,float('nan'),float('inf')])
def test_unverified_match_never_falls_back_to_estimated_box(idx):
    rows,diag=current_detection_boxes([track(idx)],[[10,20,25,60]])
    assert rows.shape==(0,8) and not diag[0]['accepted']


def test_duplicate_index_rejects_both_competing_tracks():
    rows,diag=current_detection_boxes([track(0,7),track(0,8)],[[10,20,25,60]])
    assert rows.shape==(0,8)
    assert all(d['reason']=='duplicate_detection_assignment' for d in diag)


@pytest.mark.parametrize('box',[[10,20,10,60],[10,20,25,10],[float('nan'),20,25,60]])
def test_invalid_current_measurement_is_not_observed(box):
    rows,diag=current_detection_boxes([track()], [box])
    assert not len(rows) and diag[0]['reason']=='invalid_detection_box'


def test_layout_and_empty_inputs():
    rows,diag=current_detection_boxes([track()[:5]],np.empty((0,6)))
    assert not len(rows) and diag[0]['reason']=='unsupported_tracker_layout'
    rows,diag=current_detection_boxes(np.empty((0,8)),np.empty((0,6)))
    assert rows.shape==(0,8) and diag==[]


def test_cli_blocks_reusing_old_reviewed_boundary(monkeypatch):
    import sys
    from scripts.run_live_feedback_identity import main
    monkeypatch.setattr(sys,'argv',['run_live_feedback','missing.mp4','missing.json','cam3',
        '--direction','1','--observed-detection-boxes','--reviewed-links-store','old-store'])
    with pytest.raises(SystemExit) as exc:main()
    assert exc.value.code==2


@pytest.mark.parametrize('width,height,changed',[(50,150,False),(49,150,True),(100,149,True),(201,300,True)])
def test_shape_mode_changes_only_discrepancies_above_two(width,height,changed):
    source=np.array([track()])
    detections=np.array([[0,0,width,height]])
    rows,diag=current_detection_boxes(source,detections,mode='shape-outliers')
    np.testing.assert_array_equal(rows[0,:4],detections[0] if changed else source[0,:4])
    assert diag[0]['box_basis']==('current_detection' if changed else 'tracker_estimate')


def test_identity_guard_and_review_see_tracker_geometry_before_measurement_policy():
    from scripts.run_live_feedback_identity import prepare_observation_tracks
    original=np.array([track()],dtype=float)
    calls=[]
    class Guard:
        def update(self,t,frame,rows):
            calls.append('identity')
            np.testing.assert_array_equal(rows,original)
            rows=rows.copy();rows[0,4]=1000001
            return rows,[{'action':'split'}]
    class Reconnect:
        def update(self,t,rows):
            calls.append('reconnect')
            np.testing.assert_array_equal(rows[0,:4],original[0,:4])
            assert rows[0,4]==1000001
            return {},[]
    result,events,aliases,reconnect_events,checks=prepare_observation_tracks(1,None,original,
        np.array([[10,20,25,60]]),identity_guard=Guard(),reconnect=Reconnect(),observed=True)
    assert calls==['identity','reconnect']
    assert result[0,4]==1000001
    np.testing.assert_array_equal(result[0,:4],[10,20,25,60])
    np.testing.assert_array_equal(original[0,:4],[0,0,100,300])
    assert events==[{'action':'split'}] and checks[0]['accepted']


def test_default_pipeline_does_not_apply_measurement_policy():
    from scripts.run_live_feedback_identity import prepare_observation_tracks
    original=np.array([track()],dtype=float)
    result,*_=prepare_observation_tracks(1,None,original,np.array([[10,20,25,60]]))
    np.testing.assert_array_equal(result,original)
