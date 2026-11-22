import json
import numpy as np
import pytest
from app.learned_reconnect import FEATURES,LearnedLinker,fit_scorer,score,validate_eval_group


def constant_model(bias):
    return {'features':FEATURES,'mean':[0]*9,'scale':[1]*9,'weights':[0]*9,'bias':bias,'threshold':.9,'ambiguity_margin':.15}


def test_supervised_fit_learns_features_without_ids_and_is_deterministic():
    x=np.array([[0]*9,[.1]*9,[.2]*9,[1]*9,[1.1]*9,[1.2]*9]);y=[1,1,1,0,0,0]
    model=fit_scorer(x,y)
    assert model==fit_scorer(x,y)
    assert score(model,x[0])>score(model,x[-1])
    assert len(model['features'])==9
    with pytest.raises(ValueError):fit_scorer(x,[1]*6)


def test_split_refuses_same_video_even_if_new_clip_name_is_used_as_path():
    model={'train_video_groups':['own-match']}
    with pytest.raises(ValueError):validate_eval_group(model,'own-match')
    with pytest.raises(ValueError):validate_eval_group(model,'')
    validate_eval_group(model,'another-match')


def test_linker_abstains_or_links_without_creating_boxes():
    frame=np.zeros((100,100,3),np.uint8)
    for bias,expected in [(-10,'2'),(10,'1')]:
        linker=LearnedLinker(constant_model(bias))
        for t in (0,.2,.4):linker.update(t,frame,[[10,10,30,70,1]])
        aliases,events=linker.update(.8,frame,[[11,10,31,70,2]])
        assert aliases=={'2':expected}
        assert len(events)==(bias>0)
        json.dumps(events)
        assert linker.update(1.,frame,[])[0]=={}


def test_geometry_events_are_serializable_with_numpy_tracks():
    frame=np.zeros((100,100,3),np.uint8);linker=LearnedLinker()
    for t in (0,.2,.4):linker.update(t,frame,np.array([[10,10,30,70,1]],np.float32))
    _,events=linker.update(.8,frame,np.array([[11,10,31,70,2]],np.float32))
    assert len(events)==1
    json.dumps(events)


def test_ambiguity_and_simultaneous_return_cannot_duplicate_identity():
    frame=np.zeros((100,100,3),np.uint8);linker=LearnedLinker(constant_model(10))
    for t in (0,.2,.4):linker.update(t,frame,[[10,10,30,70,1],[11,10,31,70,3]])
    assert linker.update(.8,frame,[[11,10,31,70,2]])[0]=={'2':'2'}
    linker=LearnedLinker(constant_model(10))
    for t in (0,.2,.4):linker.update(t,frame,[[10,10,30,70,1]])
    assert linker.update(.8,frame,[[11,10,31,70,2]])[0]=={'2':'1'}
    aliases,_=linker.update(1.,frame,[[11,10,31,70,2],[10,10,30,70,1]])
    assert len(set(aliases.values()))==2
