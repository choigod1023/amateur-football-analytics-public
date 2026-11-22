import json
from app.difference_review import DifferenceReview
from app.reappearance_review import reviewed_links
from app.local_redetect import search_region
import pytest


def fixture(tmp_path):
    root=tmp_path/'differences';root.mkdir()
    rows=[{'id':'d0001','kind':'tracking','review_scope':'occlusion-reappearance','source_sha256':'abc',
           'source_pair':['1','2'],'boundary':{'end':1,'start':2},'images':[]},
          {'id':'d0002','kind':'tracking','images':[]}]
    (root/'queue.json').write_text(json.dumps({'items':rows}))
    return root,rows


def test_scoped_queue_only_contains_unanswered_selected_cases(tmp_path):
    root,rows=fixture(tmp_path);review=DifferenceReview(tmp_path)
    assert review.listing(scope='occlusion-reappearance')['total']==1
    before=(root/'queue.json').read_bytes()
    review.answer('d0001','same')
    assert review.listing(scope='occlusion-reappearance')['remaining']==0
    assert review.listing()['remaining']==1
    assert (root/'queue.json').read_bytes()==before
    assert reviewed_links(tmp_path,'abc')['approved'][0]['pair']==['1','2']
    assert not reviewed_links(tmp_path,'wrong-source')['approved']


def test_stale_or_overlapping_answer_never_authorizes_join(tmp_path):
    root,rows=fixture(tmp_path);review=DifferenceReview(tmp_path);review.answer('d0001','same')
    rows[0]['boundary']['end']=3
    (root/'queue.json').write_text(json.dumps({'items':rows}))
    assert not reviewed_links(tmp_path,'abc')['approved']
    assert reviewed_links(tmp_path,'abc')['pending']==['d0001']


def test_human_negative_is_exposed_without_rewriting_labels(tmp_path):
    root,rows=fixture(tmp_path);review=DifferenceReview(tmp_path);review.answer('d0001','different')
    original=(root/'answers/d0001.json').read_bytes()
    assert reviewed_links(tmp_path,'abc')['blocked']==[['1','2']]
    assert (root/'answers/d0001.json').read_bytes()==original


def test_local_search_clips_boundaries_and_rejects_bad_box():
    assert search_region([0,0,10,20],(1080,1920,3))==(0,0,160,160)
    assert search_region([1910,1060,1920,1080],(1080,1920,3))==(1760,920,1920,1080)
    assert search_region([0,0,10,20],(50,60,3))==(0,0,60,50)
    with pytest.raises(ValueError):search_region([0,0,0,0],(1080,1920,3))
