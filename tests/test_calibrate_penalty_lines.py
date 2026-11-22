import pytest
from scripts.calibrate_penalty_lines import candidate


def sample(side='left'):
    return {'image_size_px': [1920, 1080], 'field_size_m': [105, 68], 'side': side,
            'lines': {'end': [[100, 100], [100, 700]], 'front': [[500, 100], [500, 700]],
                      'top': [[100, 100], [500, 100]], 'bottom': [[100, 700], [500, 700]]}}


@pytest.mark.parametrize('side,xs', [('left', {0., 16.5}), ('right', {105., 88.5})])
def test_candidate_is_unvalidated_and_uses_measured_axes(side, xs):
    result = candidate(sample(side))
    cal = result['calibration']
    assert cal['validated'] is False
    assert {p[0] for p in cal['field_points_m']} == xs
    assert {round(p[1], 2) for p in cal['field_points_m']} == {13.84, 54.16}


def test_rejects_bad_segments_and_missing_measured_dimensions():
    data = sample(); data['lines']['front'] = [[100.1, 100], [100.1, 700]]
    with pytest.raises(ValueError): candidate(data)
    data = sample(); data['field_size_m'] = [105, 30]
    with pytest.raises(ValueError): candidate(data)
    data = sample(); data['lines']['top'] = [[100, 100], [120, 100]]
    with pytest.raises(ValueError): candidate(data)
