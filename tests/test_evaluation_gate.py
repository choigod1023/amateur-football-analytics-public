from copy import deepcopy
from app.evaluation_gate import tracking_gate
from app.evaluation_gate import role_gate


def example():
    return {'own': {'baseline': {'matched': 100, 'unmatched_detection': 5, 'duplicate_gt_claims': 0},
                    'candidate': {'matched': 101, 'unmatched_detection': 5, 'duplicate_gt_claims': 0},
                    'paired_output_changes': {'shared_consecutive_comparisons': 50,
                                             'baseline_shared_switches': 5, 'candidate_shared_switches': 4}}}


def test_missing_own_truth_never_counts_as_success():
    result = tracking_gate(example())
    assert result['status'] == 'needs_validation'
    assert 'own_video_identity_truth' in result['missing_evidence']
    assert not result['production_approved']


def test_recall_gain_does_not_hide_unmatched_regression():
    groups = example()
    groups['own']['candidate']['unmatched_detection'] = 9
    result = tracking_gate(groups, independent=True, own_identity_verified=True)
    assert result['status'] == 'regression'
    assert result['regressions'][0]['metric'] == 'own.unmatched_detection'


def test_null_nan_and_impossible_denominators_require_evidence():
    for value in (None, float('nan'), -1, True):
        groups = deepcopy(example())
        groups['own']['candidate']['matched'] = value
        assert tracking_gate(groups, independent=True, own_identity_verified=True)['status'] == 'needs_validation'
    groups = example()
    groups['own']['paired_output_changes']['shared_consecutive_comparisons'] = 2
    assert tracking_gate(groups)['status'] == 'needs_validation'


def test_valid_improvement_only_qualifies_for_shadow_test():
    result = tracking_gate(example(), independent=True, own_identity_verified=True)
    assert result['status'] == 'eligible_for_shadow_test'
    assert result['production_approved'] is False
    assert tracking_gate({})['status'] == 'needs_validation'


def test_role_accuracy_gain_cannot_hide_spectator_as_player_error():
    old = {'confusion': [[20, 10, 0, 0], [5, 95, 3, 5], [0, 1, 10, 0], [0, 0, 0, 10]]}
    new = deepcopy(old)
    new['confusion'][0] = [25, 5, 0, 0]
    new['confusion'][1] = [4, 95, 4, 5]
    result = role_gate(old, new, ['referee', 'spectator', 'team_a', 'team_b'])
    assert result['correct_after'] > result['correct_before']
    assert result['status'] == 'regression'
    assert result['regressions'][0]['metric'] == 'spectator_as_player'
    assert role_gate({}, {}, [])['status'] == 'needs_validation'
