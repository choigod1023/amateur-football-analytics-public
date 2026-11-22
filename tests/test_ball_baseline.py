import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_ball_baseline import score
from train_ball_rerank import chain_metrics


def test_false_alarms_are_in_overall_precision():
    result = chain_metrics(dict(right=249, wrong=20, on_empty=140, ball_frames=612, empty_frames=1140))
    assert result['precision'] == result['conditional_precision_ball_present'] == .926
    assert result['overall_precision'] == .609


def test_rejected_unknown_and_unverified_do_not_become_negatives():
    labels = {'a': {'state': 'ball', 'verified': 'ok', 'x': 10, 'y': 20},
              'b': {'state': 'none'}, 'c': {'state': 'ball', 'verified': 'rejected'},
              'd': {'state': 'unsure'}, 'e': {'state': 'ball'}}
    result = score(labels, {name: (10, 20) for name in labels})
    assert result['precision'] == .5
    assert result['correct'] == result['false_on_empty'] == 1
    assert result['excluded'] == 3


def test_missing_ball_and_no_answer_have_explicit_denominators():
    result = score({'a': {'state': 'ball', 'verified': 'moved', 'x': 1, 'y': 2}}, {})
    assert result['precision'] is None
    assert result['recall'] == 0
    assert result['missed'] == 1
