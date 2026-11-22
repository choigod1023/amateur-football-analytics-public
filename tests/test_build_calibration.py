import pytest
from scripts.build_calibration import build


def fixture():
    return {'image_size_px': [1000, 500], 'field_size_m': [100, 50],
            'fitting_points': [
                {'image_point': [900, 450], 'field_point_m': [100, 50]},
                {'image_point': [100, 50], 'field_point_m': [0, 0]},
                {'image_point': [900, 50], 'field_point_m': [100, 0]},
                {'image_point': [100, 450], 'field_point_m': [0, 50]},
                {'image_point': [500, 250], 'field_point_m': [50, 25]}],
            'checkpoints': [{'image_point': [300, 150], 'field_point_m': [25, 12.5]}]}


def test_unordered_points_and_independent_check():
    result = build(fixture())
    assert result['calibration']['validated'] is False
    assert set(result['fitting_indices']) == {0, 1, 2, 3}
    assert result['unused_fitting_indices'] == [4]
    assert result['independent_checkpoint_report']['max_error_m'] == 0
    assert result['unused_fitting_consistency']['max_error_m'] == 0


def test_unused_fitting_inconsistency_report_is_not_validation():
    data = fixture()
    data['fitting_points'][4]['field_point_m'] = [60, 25]
    result = build(data)
    assert result['calibration']['validated'] is False
    assert result['independent_checkpoint_report']['max_error_m'] == 0
    assert result['unused_fitting_consistency']['max_error_m'] == 10
    assert result['unused_fitting_consistency']['validated'] is False


def test_duplicate_checkpoint_and_impossible_geometry():
    data = fixture(); data['checkpoints'] = [data['fitting_points'][4]]
    with pytest.raises(ValueError): build(data)
    data = fixture(); data['fitting_points'] = data['fitting_points'][:4]
    data['fitting_points'][0]['field_point_m'] = [50, 10]
    with pytest.raises(ValueError): build(data)


def test_refuse_outside_points_and_invalid_dimensions():
    data = fixture(); data['fitting_points'][0]['image_point'] = [-1, 2]
    with pytest.raises(ValueError): build(data)
    data = fixture(); data['field_size_m'] = [100, 0]
    with pytest.raises(ValueError): build(data)
