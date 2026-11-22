import numpy as np
import pytest
from unittest.mock import patch
from app.temporal_reconnect import TemporalLinker, aggregate
from app.global_temporal_reconnect import GlobalTemporalLinker

@pytest.mark.parametrize('cls', [TemporalLinker, GlobalTemporalLinker])
def test_overlap_clears_contaminated_history_without_late_alias(cls):
    link = cls({'threshold':.9, 'ambiguity_margin':.15, 'max_prediction_residual_heights':1.5})
    module = cls.__module__
    with patch(module+'.descriptor', return_value=[np.array([1.,0.])]*6) as extract:
        for t in (0., .2): link.update(t,None,[[0,0,10,20,1]])
        calls = extract.call_count
        mapping, events = link.update(.4,None,[[0,0,10,20,1],[2,0,12,20,2]])
        assert extract.call_count == calls
        assert mapping == {'1':'1','2':'2'} and not events
        assert not link.memory['1']['history']
        for t in (.6,.8,1.):
            mapping, events=link.update(t,None,[[0,0,10,20,1],[30,0,40,20,2]])
            assert not events
        assert [r['time'] for r in link.memory['1']['history']]==[.6,.8,1.]
        assert mapping == {'1':'1','2':'2'}

def test_aggregate_rejects_explicitly_crowded_evidence():
    rows=[{'time':t,'crowded':True,'descriptor':[np.array([1.,0.])]*6,'box':[0,0,10,20]} for t in (0,.2,.4)]
    assert aggregate(rows) is None
