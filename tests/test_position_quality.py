import numpy as np
import pytest
from app.position_quality import position_quality, calibration_diagnostics
from app.pitch_map import feet_to_metres


def fitted(h=None):
    return {'H': np.eye(3) if h is None else np.array(h, float), 'pitch': {'length':100.,'width':100.}}


def test_affine_exact_envelope_and_jacobian():
    q = position_quality(fitted(), [1,1,3,4], 1,1)
    assert q['foot_envelope_radius_m'] == pytest.approx(3*2**.5)
    assert np.allclose(q['jacobian_m_per_px'], np.eye(2))
    assert not q['tactical_foot_gate']


def test_boundary_and_outside_are_not_clamped():
    q = position_quality(fitted(), [47,1,49,4],1,1)
    assert q['boundary'] == 'boundary_uncertain'
    q = position_quality(fitted(), [50,1,52,4],1,1)
    assert q['boundary'] == 'outside'
    assert q['position_m'][0] == 51


@pytest.mark.parametrize('h', [np.zeros((3,3)), [[1,0,0],[0,1,0],[0,-1,4]]])
def test_degenerate_and_horizon_rejected(h):
    assert not position_quality(fitted(h),[1,1,3,4],1,1)['valid']


def test_nonfinite_input_and_calibration():
    assert not position_quality(fitted(),[1,1,3,float('nan')],1,1)['valid']
    assert not calibration_diagnostics({'points': []})['valid']


def test_perspective_jacobian_matches_numeric_derivative():
    h = [[1,0,0],[0,1,0],[0,.01,1]]
    box = np.array([1,1,3,4.])
    q = position_quality(fitted(h),box,1,1)
    eps = 1e-5
    for axis in range(2):
        moved = box.copy()
        moved[[0,2] if axis == 0 else [3]] += eps
        shifted = position_quality(fitted(h),moved,1,1)
        numeric = (np.array(shifted['position_m'])-q['position_m'])/eps
        assert np.allclose(numeric,np.array(q['jacobian_m_per_px'])[:,axis],atol=1e-6)


@pytest.mark.parametrize('bad', [None, [1,2], [[1,2],[3,4]], 'bad'])
def test_invalid_box_shapes(bad):
    assert not position_quality(fitted(),bad,1,1)['valid']


def test_invalid_transform_shapes():
    assert not position_quality(fitted(),[1,1,3,4],1,1,bg=[1,2])['valid']
    assert not position_quality({'H': [1,2], 'pitch': {'length':100,'width':100}},[1,1,3,4],1,1)['valid']


def test_background_shift_matches_existing_projection():
    f = fitted([[20,0,-10],[0,15,-7],[0,.05,1]])
    box = [550,400,600,700]
    options = dict(width=1920,height=1080,shift=(-1.8,6.8),bg=(1.003087,-.001614,-7.41,5.61))
    assert np.allclose(position_quality(f,box,**options)['position_m'],feet_to_metres(f,box,**options))
