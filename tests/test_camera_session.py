import json

import numpy as np
import pytest

from app.camera_session import CameraSession


FRAME = np.zeros((100, 100, 3), np.uint8)
RECORD = {'points': [{'x': x, 'y': y} for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]}
FITTED = {'H': np.diag([10., 10., 1.]), 'pitch': {'length': 89, 'width': 60}, 'rms': .3}


def registration(scale=1., dx=0.):
    matrix = np.array([[scale, 0, dx], [0, scale, 0], [0, 0, 1.]])
    return {'status': 'ready', 'reason': 'validated_pitch_correspondences',
            'reference_to_current': matrix.tolist(), 'current_to_reference': np.linalg.inv(matrix).tolist(),
            'reference_size': [100, 100], 'current_size': [100*scale, 100*scale],
            'support_polygon_current': [[dx, 0], [100*scale+dx, 0], [100*scale+dx, 100*scale], [dx, 100*scale]]}


class Registrar:
    def __init__(self):
        self.result = registration()
        self.references = []

    def fit(self, reference, current, polygon):
        self.references.append(reference)
        return self.result


def session(**kwargs):
    registrar = Registrar()
    return CameraSession(FRAME, RECORD, FITTED, registrar=registrar, **kwargs), registrar


def test_requires_confirmation_and_never_reuses_failed_mapping():
    camera, registrar = session()
    assert camera.update(FRAME)['state'] == 'stabilizing'
    assert camera.point([10, 10, 20, 20], FRAME) is None
    assert camera.update(FRAME)['state'] == 'ready'
    assert camera.point([10, 10, 20, 20], FRAME) == pytest.approx((1.5, 2))
    registrar.result = {'status': 'needs_review', 'reason': 'insufficient_features'}
    assert camera.update(FRAME)['reset_temporal']
    assert camera.point([10, 10, 20, 20], FRAME) is None
    registrar.result = registration()
    assert camera.update(FRAME)['state'] == 'stabilizing'
    assert camera.update(FRAME)['state'] == 'ready'
    assert all(ref is FRAME for ref in registrar.references)


def test_camera_motion_resets_then_transfers_feet_without_extrapolation():
    camera, registrar = session()
    camera.update(FRAME)
    camera.update(FRAME)
    registrar.result = registration(dx=20)
    state = camera.update(FRAME)
    assert state['state'] == 'stabilizing' and state['reset_temporal']
    assert camera.point([30, 10, 40, 20], FRAME) is None
    assert camera.update(FRAME)['state'] == 'ready'
    assert camera.point([30, 10, 40, 20], FRAME) == pytest.approx((1.5, 2))
    assert camera.point([0, 10, 10, 20], FRAME) is None


def test_resize_preserves_coordinates_and_saved_pitch_dimensions():
    camera, registrar = session()
    camera.update(FRAME)
    camera.update(FRAME)
    registrar.result = registration(scale=2)
    resized = np.zeros((200, 200, 3), np.uint8)
    state = camera.update(resized)
    assert state['state'] == 'ready' and not state['reset_temporal']
    assert state['pitch']['width'] == 60
    assert state['pitch_dimensions_are_estimates']
    assert state['reference_rms_m'] == .3
    assert camera.point([20, 20, 40, 40], resized) == pytest.approx((1.5, 2))


def test_freezes_one_review_preserves_existing_answers_and_writes_safe_status(tmp_path):
    answers = tmp_path / 'labels.jsonl'
    answers.write_text('existing answer', encoding='utf-8')
    camera, registrar = session(review_store=tmp_path)
    registrar.result = {'status': 'needs_review', 'reason': 'insufficient_features'}
    for i in range(3):
        camera.update(FRAME, i)
    assert len(list((tmp_path / 'pending').glob('*.json'))) == 1
    assert len(list((tmp_path / 'pending').glob('*.jpg'))) == 1
    assert answers.read_text(encoding='utf-8') == 'existing answer'
    assert camera.status['review_page'] == '/train'
    path = tmp_path / 'alerts.camera.json'
    camera.write_status(path)
    stored = json.loads(path.read_text(encoding='utf-8'))
    assert stored['state'] == 'needs_review'
    assert 'current_to_reference' not in stored and 'source' not in stored


def test_missing_reference_refuses_and_token_cannot_escape_store(tmp_path):
    camera = CameraSession.from_record(tmp_path / 'calibration' / 'maps.json',
                                      {**RECORD, 'ref_token': '../../secret'}, FITTED)
    assert camera.update(FRAME)['reason'] == 'calibration_reference_unavailable'
    assert camera.point([10, 10, 20, 20], FRAME) is None


def test_invalid_transfer_does_not_leave_mapping_ready():
    camera, registrar = session()
    camera.update(FRAME)
    registrar.result['support_polygon_current'] = 'invalid'
    assert camera.update(FRAME)['state'] == 'needs_review'
    assert camera.mapping is None


def test_status_serializes_stable_and_moving_ready_transitions(tmp_path):
    camera, registrar = session()
    path = tmp_path / 'alerts.camera.json'
    for expected in ('stabilizing', 'ready', 'ready'):
        camera.update(FRAME)
        camera.write_status(path)
        status = json.loads(path.read_text(encoding='utf-8'))
        assert status['state'] == expected
        assert status['reset_temporal'] is False
    registrar.result = registration(dx=20)
    camera.update(FRAME)
    camera.write_status(path)
    status = json.loads(path.read_text(encoding='utf-8'))
    assert status['state'] == 'stabilizing'
    assert status['reset_temporal'] is True
    camera.update(FRAME)
    camera.write_status(path)
    assert json.loads(path.read_text(encoding='utf-8'))['state'] == 'ready'
