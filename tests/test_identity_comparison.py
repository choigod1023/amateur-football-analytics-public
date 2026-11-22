import importlib.util
from pathlib import Path
import sys

import pytest

scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
from evaluate_identity_retraining import validate_comparison, validate_source_hash, publication_mapping, score_frame


def model():
    return dict(train_video_groups=['training_match'], features=['appearance'],
                threshold=.9, ambiguity_margin=.15, confirmation_frames=3,
                output_delay_frames=2, max_prediction_residual_heights=1.5)


def test_both_model_groups_are_checked():
    a,b=model(),model()
    validate_comparison(a,b,'eval_match')
    b['train_video_groups'] += ['eval_match']
    with pytest.raises(ValueError):
        validate_comparison(a,b,'eval_match')


def test_source_content_cannot_leak_under_another_group_name():
    with pytest.raises(ValueError): validate_source_hash({},'abc')
    with pytest.raises(ValueError): validate_source_hash({'train_source_sha256':['abc']},'abc')
    validate_source_hash({'train_source_sha256':['train']},'eval')


@pytest.mark.parametrize('field,value', [('threshold',.8),('output_delay_frames',3),('features',['new'])])
def test_policy_changes_cannot_masquerade_as_retraining(field,value):
    a,b=model(),model();b[field]=value
    with pytest.raises(ValueError):
        validate_comparison(a,b,'eval_match')


def test_conflicting_buffered_aliases_are_not_published_as_two_same_players():
    class Linker:
        def resolve(self, raw): return 'prior'
    assert publication_mapping(['1','2'],Linker())=={'1':'1','2':'2'}


def test_identity_changes_are_scored_without_changing_observation_counts():
    total={k:0 for k in ('id_switches','return_same','return_switched','matched','missed_gt','unmatched_detection')}
    memory={}
    item=dict(targets=[('player',[0,0,5,5])],matches=[('player','1')],raw_ids=['1'],step=0)
    score_frame(item,{'1':'old'},memory,total)
    item['step']=2
    score_frame(item,{'1':'new'},memory,total)
    assert total['id_switches']==total['return_switched']==1
    assert total['matched']==2 and total['missed_gt']==total['unmatched_detection']==0
