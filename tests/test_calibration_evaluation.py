import pytest
from scripts.evaluate_calibration import evaluate


def test_known_error_and_outside_are_reported_without_automatic_validation():
    cal = {'image_points': [[0, 0], [100, 0], [100, 100], [0, 100]],
           'field_points_m': [[0, 0], [100, 0], [100, 50], [0, 50]], 'field_size_m': [100, 50]}
    checks = [{'image_point': [50, 50], 'field_point_m': [53, 29]},
              {'image_point': [110, 50], 'field_point_m': [99, 25]}]
    result = evaluate(cal, checks)
    assert result['median_error_m'] == result['max_error_m'] == 5.0
    assert result['measured'] == 1 and result['total'] == 2
    assert result['checkpoints'][1]['reason'] == 'outside_calibrated_area'
    assert result['validated'] is False
    with pytest.raises(ValueError, match='duplicates'):
        evaluate(cal, [{'image_point': [0, 0], 'field_point_m': [0, 0]}])
