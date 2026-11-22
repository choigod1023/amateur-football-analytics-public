import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('prepare_identity_retraining', Path(__file__).parents[1]/'scripts/prepare_identity_retraining.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_human_fingerprint_required():
    item = {'id': 'd0113', 'kind': 'tracking'}
    answer = {'id': 'd0113', 'source': 'human', 'fingerprint': module.fingerprint(item), 'verdict': 'same'}
    assert module.verified_label(item, answer) == 1
    assert module.verified_label(item, {**answer, 'verdict': 'different'}) == 0
    assert module.verified_label(item, {**answer, 'verdict': 'unclear'}) is None
    with pytest.raises(ValueError):
        module.verified_label({**item, 'title': 'changed'}, answer)
    with pytest.raises(ValueError):
        module.verified_label(item, {**answer, 'source': 'model'})


def test_candidate_requires_exact_reviewed_geometry_and_unique_match():
    q = {'a': '1', 'b': '2', 'end': 1., 'start': 2., 'before_box': [0,0,1,2], 'after_box': [1,0,2,2]}
    item = {'source_pair': ['1','2'], 'boundary': q}
    assert module.match_candidate(item, [q]) == q
    with pytest.raises(ValueError):
        module.match_candidate(item, [q,q])
    with pytest.raises(ValueError):
        module.match_candidate(item, [{**q, 'before_box': [2,0,3,2]}])


def test_trace_does_not_relabel_nearby_frame_as_reviewed_endpoint():
    item = {'source_pair': ['1','2'], 'boundary': {'end':1.,'start':2.,'before_box':[0,0,1,2],'after_box':[1,0,2,2]}}
    frames = [{'time':.8, 'source_tracks':[[0,0,1,2,1]]}, {'time':2.,'source_tracks':[[1,0,2,2,2]]}]
    with pytest.raises(ValueError):
        module.trace_candidate(item, frames)


def test_sparse_training_history_cannot_imply_runtime_eligibility():
    pair = {'before': [{'time': t} for t in (29.4,30.2,30.4,31.4,31.6)],
            'after': [{'time': t} for t in (32.2,32.4,32.6)]}
    result = module.runtime_history(pair)
    assert result['before']['training_count'] == 5
    assert result['before']['retained_count'] == 2
    assert not result['eligible']


def test_after_birth_gap_prevents_runtime_eligibility():
    pair = {'before': [{'time':t} for t in (0,.2,.4)],
            'after': [{'time':t} for t in (1.,1.4,1.6)]}
    assert not module.runtime_history(pair)['eligible']
