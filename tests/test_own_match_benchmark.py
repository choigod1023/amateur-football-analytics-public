import pytest

from app.difference_review import fingerprint
from scripts.build_own_match_benchmark import free_windows, identity_groups, interval, overlaps, verified_identity


def item(ident='d0108'):
    return {'id':ident,'kind':'tracking','source_sha256':'abc','source_pair':['1','2'],
            'boundary':{'end':1.,'start':2.,'before_box':[0,0,1,1],'after_box':[0,0,1,1]}}


def test_only_fingerprinted_human_answer_is_reused():
    row=item(); answer={'source':'human','id':row['id'],'verdict':'same','fingerprint':fingerprint(row)}
    assert verified_identity(row,answer,'abc')['verdict']=='same'
    for change in ({'source':'model'},{'verdict':'unclear'},{'fingerprint':'old'},{'id':'d9999'}):
        with pytest.raises(ValueError): verified_identity(row,{**answer,**change},'abc')
    with pytest.raises(ValueError): verified_identity(row,answer,'another-video')


def test_full_buffer_excludes_nearby_and_containing_samples():
    gaps=free_windows(0,300,[interval(100,110),interval(200,210)],60)
    assert gaps==[interval(0,40),interval(270,300)]
    assert overlaps(interval(50,80),interval(100,110),60)
    assert not overlaps(interval(10,20),interval(100,110),60)


def test_known_identity_chain_cannot_cross_split_groups():
    rows=[{'id':'a','tracks':['1','2'],'source_sha256':'v','clip_interval':interval(0,1)},
          {'id':'b','tracks':['2','3'],'source_sha256':'v','clip_interval':interval(100,101)},
          {'id':'c','tracks':['7','8'],'source_sha256':'v','clip_interval':interval(104,105)},
          {'id':'d','tracks':['1','2'],'source_sha256':'other','clip_interval':interval(0,1)}]
    assert identity_groups(rows)==[['a','b','c'],['d']]


@pytest.mark.parametrize('start,end',[(3,2),(-1,2),(float('nan'),2),(1,float('inf'))])
def test_invalid_times_fail_closed(start,end):
    with pytest.raises(ValueError): interval(start,end)
