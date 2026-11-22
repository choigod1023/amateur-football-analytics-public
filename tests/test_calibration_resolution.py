import pytest
from app.main import active_calibration, project, validate_config


def test_resolution_guard_refuses_unverified_or_mismatched_video():
    cal = {'validated': True, 'image_points': [[0,0],[100,0],[100,100],[0,100]],
           'field_points_m': [[0,0],[100,0],[100,50],[0,50]], 'field_size_m':[100,50]}
    validate_config({'calibration': cal})
    guarded, reason = active_calibration(cal, (100,100,3))
    assert guarded is None and reason == 'resolution_unverified'
    assert project((50,50), guarded) == (None, None)
    cal['image_size_px'] = [100,100]
    guarded, reason = active_calibration(cal, (100,100,3))
    assert reason == 'active' and project((50,50), guarded) == (.5,.5)
    guarded, reason = active_calibration(cal, (200,200,3))
    assert guarded is None and reason == 'resolution_mismatch'
    assert project((50,50), guarded) == (None,None)
    cal['validated'] = False
    assert active_calibration(cal, (100,100,3))[1] == 'not_validated'
    assert active_calibration(None, (100,100,3))[1] == 'not_configured'
    cal['image_size_px'] = [True,100]
    with pytest.raises(ValueError): validate_config({'calibration':cal})
