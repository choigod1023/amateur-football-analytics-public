from copy import deepcopy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compare_minimap_pipeline import compare


def trace():
    return [{'time': i*.2, 'source_tracks': [[0, 0, 10, 20, 1]],
             'raw_positions': {'home': [(1, x, 0)], 'away': []}}
            for i, x in enumerate((0., 10., .1))]


def test_role_and_position_effects_stay_separate():
    old = trace()
    new = deepcopy(old)
    new[1]['raw_positions']['home'] = []
    result = compare(old, new)
    base = result['results']['baseline_role']
    assert base['old_position_guard']['retained'] == 1
    assert base['fixed_position_guard']['retained'] == 2
    assert result['identity_accuracy'] is None
    assert result['true_position_error_m'] is None
    assert not result['production_approved']


def test_changed_tracker_or_time_invalidates_role_only_claim():
    old, new = trace(), trace()
    new[1]['source_tracks'][0][4] = 2
    with pytest.raises(ValueError, match='outputs differ'):
        compare(old, new)
    with pytest.raises(ValueError, match='frame count'):
        compare(old, new[:-1])
