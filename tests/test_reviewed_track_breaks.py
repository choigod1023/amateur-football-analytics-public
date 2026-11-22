import pytest
from app.reviewed_track_breaks import split_reviewed_tracks


def sample():
    return {'tracks':{'1':[{'frame':i,'team':'B','box':[1,2,3,4]} for i in range(4)]}}


def test_only_different_splits_and_preserves_geometry_and_source():
    data=sample()
    result, applied=split_reviewed_tracks(data, {'1':[{'frame':2,'verdict':'different'}]})
    assert len(data['tracks']['1'])==4
    assert result['tracks']['1']==data['tracks']['1'][:2]
    assert result['tracks']['2']==data['tracks']['1'][2:]
    assert len(applied)==1
    assert split_reviewed_tracks(data, {'1':[{'frame':2,'verdict':'same'}]})[0]==data


def test_estimated_boundary_is_not_human_observation():
    data=sample();data['tracks']['1'][1]['interpolated']=True
    with pytest.raises(ValueError):
        split_reviewed_tracks(data,{'1':[{'frame':2,'verdict':'different'}]})
