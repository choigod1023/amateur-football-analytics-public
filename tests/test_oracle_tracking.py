import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluate_oracle_tracking import targets,oracle_detections,run


def test_ground_truth_identity_is_not_in_tracker_input():
    a=oracle_detections([('123',[1,2,3,4])])
    b=oracle_detections([('999',[1,2,3,4])])
    assert np.array_equal(a,b)
    assert a.tolist()==[[1.,2.,3.,4.,1.,0.]]


def test_empty_boxes_and_invisible_annotations():
    assert oracle_detections([]).shape==(0,6)
    assert targets([{'id':1,'tag':[1,2,3,4],'jump':True}])==[]


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):targets([{'id':1,'tag':[1,2,3,4]}]*2)


def test_missing_15hz_annotations_cannot_be_interpolated():
    with pytest.raises(ValueError,match='Missing annotation'):
        run({0:[]},(1080,1920),15)


def test_nonfinite_annotations_rejected():
    with pytest.raises(ValueError):targets([{'id':1,'tag':[1,2,float('nan'),4]}])


def test_consecutive_identity_denominator():
    from evaluate_oracle_tracking import consecutive_identity_counts
    assert consecutive_identity_counts({'a':'1','b':'2'},{'a':'3','c':'4'}) == (1,1)
    assert consecutive_identity_counts({}, {'a':'1'}) == (0,0)


def test_perfect_stationary_boxes_have_no_identity_switches(monkeypatch):
    import evaluate_oracle_tracking as module
    monkeypatch.setattr(module, 'WINDOWS', [(0,1)])
    labels={i:[{'id':7,'tag':[100,100,20,60]}] for i in range(0,30,2)}
    for rate in (5,15):
        result=module.run(labels,(1080,1920),rate)
        assert result['current_detection_results']['matched'] == 5
        assert result['current_detection_results']['id_switches'] == 0
        assert result['consecutive_current_identity'] == {'comparisons':4,'switches':0}
