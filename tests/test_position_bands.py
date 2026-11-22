from scripts.experimental_position_bands import bands, compare


def tracks(n=9):
    return {str(i): [(t, i/(n-1)) for t in range(25)] for i in range(n)}


def test_requires_time_coverage_direction_and_observed_roster():
    t=tracks()
    assert bands(t,0)=={}
    assert bands({k:v[:8] for k,v in t.items()},1)=={}
    assert bands(dict(list(t.items())[:5]),1)=={}
    assert bands(t,1)['0']=='back' and bands(t,1)['8']=='front'
    assert bands(t,-1)['0']=='front' and bands(t,-1)['8']=='back'
    assert compare(bands(t,1),bands(t,-1))['changed_band']==6


def test_ties_at_band_boundary_are_not_resolved_by_id():
    t=tracks(6);t['1']=t['2']
    assert '1' not in bands(t,1) and '2' not in bands(t,1)
