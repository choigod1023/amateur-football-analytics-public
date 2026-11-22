import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('dropout_prepare',Path(__file__).parents[1]/'scripts/prepare_dropout_review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def question():
    return {'a':'1','b':'2','end':1.,'start':2.,'before_box':[20,20,30,50],'after_box':[22,20,32,50]}


def test_temporal_order_and_same_raw_id_are_not_questions():
    for changes in ({'start':.5},{'start':float('nan')},{'b':'1'},{'before_box':[-1,20,30,50]}):
        with pytest.raises(ValueError):module.validate({**question(),**changes},1920,1080,60)


def test_existing_same_boundary_reused_even_when_ids_changed():
    q=question();row={'id':'d0001','kind':'tracking','source_sha256':'video','source_pair':['old1','old2'],'boundary':{k:q[k] for k in ('end','start','before_box','after_box')}}
    assert module.existing_question(q,[row],'video')=='d0001'
    assert module.existing_question(q,[row],'other-video') is None
    assert module.existing_question({**q,'start':3},[row],'video') is None


def test_pending_and_answered_status_does_not_force_repeat():
    q=question();row={'id':'d0001','kind':'tracking','source_sha256':'video','source_pair':['1','2'],'boundary':{'end':1.,'start':2.}}
    for answer in (None,{'verdict':'same'},{'verdict':'different'},{'verdict':'unclear'}):
        assert module.existing_question(q,[{**row,'answer':answer}],'video')=='d0001'


def test_zoom_keeps_endpoints_and_clips_to_source():
    q=question();q['before_box']=[0,1,10,25];q['after_box']=[60,10,70,35]
    x,y,size=module.zoom_region(q,1920,1080)
    assert x>=0 and y>=0 and x+size<=1920 and y+size<=1080
    for box in (q['before_box'],q['after_box']):
        assert x<=box[0]<box[2]<=x+size
        assert y<=box[1]<box[3]<=y+size


def test_iou_distinguishes_neighboring_people():
    assert module.iou([0,0,10,20],[0,0,10,20])==1
    assert module.iou([0,0,10,20],[11,0,21,20])==0


def test_distant_endpoints_are_not_silently_cropped_away():
    q=question();q['before_box']=[0,1,10,25];q['after_box']=[1800,10,1820,35]
    with pytest.raises(ValueError):module.zoom_region(q,1920,1080)
