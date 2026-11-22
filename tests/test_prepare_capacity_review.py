import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('capacity_review', Path(__file__).resolve().parents[1]/'scripts/prepare_capacity_review.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Capture:
    def __init__(self, path): pass
    def isOpened(self): return True
    def get(self, prop): return 10 if prop == module.cv2.CAP_PROP_FPS else 100
    def set(self, *args): pass
    def read(self): return True, np.zeros((100, 200, 3), dtype=np.uint8)
    def release(self): pass


def test_append_is_idempotent_and_does_not_label_or_change_existing_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(module.cv2, 'VideoCapture', Capture)
    video=tmp_path/'video.mp4'; video.write_bytes(b'fake recording')
    store=tmp_path/'store'; store.mkdir()
    old=store/'human.json'; old.write_bytes(b'{"answer":"preserve"}')
    selected=[{'time_s':2.,'raw_id':'430','box':[50,20,60,45], 'clip_time_s':1952.,
               'review_reason':'one_box_contains_multiple_people'}]
    a=module.prepare(selected, video, store, tmp_path/'output')
    b=module.prepare(selected, video, store, tmp_path/'output')
    assert a['questions'][0]['token'] == b['questions'][0]['token']
    assert b['questions'][0]['status'] == 'existing'
    assert old.read_bytes() == b'{"answer":"preserve"}'
    assert len(list(store.glob('*.json'))) == 1
    assert len(list((store/'pending').glob('*.json'))) == 1
    metadata=json.loads(next((store/'pending').glob('*.json')).read_text(encoding='utf-8'))
    assert len(metadata['people']) == 1 and metadata['people'][0]['id'] == '430'
    assert metadata['source_provenance']['split'] == 'train'
    assert len(list((tmp_path/'output').glob('*.jpg'))) == 3


def test_invalid_candidate_fails_before_publishing(tmp_path, monkeypatch):
    monkeypatch.setattr(module.cv2, 'VideoCapture', Capture)
    video=tmp_path/'video.mp4'; video.write_bytes(b'fake recording')
    store=tmp_path/'store'
    with pytest.raises(ValueError):
        module.prepare([{'time':2,'track_id':'x','bbox':[50,20,250,45]}],video,store,tmp_path/'output')
    assert not list(store.rglob('*.json'))


def test_same_time_people_share_one_question_and_remain_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(module.cv2, 'VideoCapture', Capture)
    video=tmp_path/'video.mp4';video.write_bytes(b'fake')
    store=tmp_path/'store'
    selected=[{'time':2,'track_id':i,'bbox':[x,20,x+10,45]} for i,x in [('a',50),('b',80)]]
    a=module.prepare(selected,video,store,tmp_path/'output')
    b=module.prepare(selected,video,store,tmp_path/'output')
    assert len({q['token'] for q in a['questions']}) == 1
    assert len(list((store/'pending').glob('*.json'))) == 1
    assert all(q['status']=='existing' for q in b['questions'])
