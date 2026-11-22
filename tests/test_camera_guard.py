import cv2
import numpy as np
import threading
from types import SimpleNamespace
import torch
import ultralytics
import pytest
from app import main
from app.camera_guard import CameraMotionGuard


def textured_frame():
    rng = np.random.default_rng(203)
    image = np.zeros((540, 960, 3), dtype=np.uint8)
    image[:] = (40, 110, 45)
    for x, y in rng.integers([40, 40], [920, 500], size=(300, 2)):
        cv2.circle(image, (int(x), int(y)), 3, (220, 220, 220), -1)
    return image


def test_static_translation_and_missing_evidence(tmp_path):
    image = textured_frame()
    path = tmp_path / 'calibration.png'; assert cv2.imwrite(str(path), image)
    guard = CameraMotionGuard(path, [[5, 5], [954, 5], [954, 534], [5, 534]])
    assert guard.check(image) == 'stable'
    shifted = cv2.warpAffine(image, np.float32([[1, 0, 12], [0, 1, 0]]), (960, 540))
    assert guard.check(shifted) == 'camera_moved'
    assert guard.check(np.zeros_like(image)) == 'camera_guard_insufficient'
    assert guard.check(np.zeros((270, 480, 3), np.uint8)) == 'camera_guard_insufficient'
    assert CameraMotionGuard(tmp_path / 'missing.png', [[0,0],[1,0],[1,1],[0,1]]).check(image) == 'camera_reference_unavailable'


def test_blank_reference_is_not_treated_as_fixed(tmp_path):
    image = np.zeros((100, 100, 3), np.uint8)
    path = tmp_path / 'blank.png'; assert cv2.imwrite(str(path), image)
    assert CameraMotionGuard(path, [[0,0],[99,0],[99,99],[0,99]]).check(image) == 'camera_reference_unavailable'


def test_separate_static_feature_region_does_not_expand_projection():
    cal = {'validated': True, 'image_size_px': [200, 100], 'field_size_m': [100, 50],
           'image_points': [[50, 25], [150, 25], [150, 75], [50, 75]],
           'field_points_m': [[0, 0], [100, 0], [100, 50], [0, 50]],
           'camera_guard_reference': 'reference.jpg',
           'camera_guard_feature_region': [[0, 0], [199, 0], [199, 99], [0, 99]]}
    main.validate_config({'calibration': cal})
    assert main.project((30, 50), cal) == (None, None)
    assert main.project((100, 50), cal) == (.5, .5)
    for region in ([[0, 0], [199, 0], [199, 99], [201, 99]],
                   [[0, 0], [10, 0], [0, 10], [10, 10]],
                   [[0, 0], [1, 0], [1, 1], [0, 1]]):
        with pytest.raises(ValueError):
            main.validate_config({'calibration': {**cal, 'camera_guard_feature_region': region}})
    with pytest.raises(ValueError):
        main.validate_config({'calibration': {**cal, 'camera_guard_reference': None}})


def test_movement_blocks_actual_pipeline_coordinates(tmp_path, monkeypatch):
    path = tmp_path / 'video.mp4'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (160, 100))
    assert writer.isOpened()
    for _ in range(3): writer.write(np.full((100, 160, 3), 60, np.uint8))
    writer.release()
    class FakeModel:
        names = {0: 'person'}
        def track(self, *args, **kwargs):
            boxes = SimpleNamespace(id=torch.tensor([7]), xyxy=torch.tensor([[40., 10., 80., 90.]]))
            return [SimpleNamespace(boxes=boxes)]
    monkeypatch.setattr(ultralytics, 'YOLO', lambda *args, **kwargs: FakeModel())
    monkeypatch.setattr(CameraMotionGuard, 'check', lambda self, frame: 'camera_moved')
    monkeypatch.setattr(main, 'stop_event', threading.Event())
    monkeypatch.setattr(main, 'status', {})
    monkeypatch.setattr(main, 'analysis', {})
    monkeypatch.setattr(main, 'preview', {})
    cal = {'validated':True, 'image_size_px':[160,100], 'field_size_m':[100,50],
           'image_points':[[0,0],[159,0],[159,99],[0,99]],
           'field_points_m':[[0,0],[100,0],[100,50],[0,50]],
           'camera_guard_reference':str(tmp_path / 'missing.png')}
    main.run(str(path), {'calibration':cal, 'team_classification_validated':True})
    assert main.status['status'] == 'idle'
    assert main.analysis['calibration_status'] == 'camera_moved'
    assert main.analysis['players'][0]['x'] is None and main.analysis['players'][0]['y'] is None
    assert main.analysis['metrics']['team_width_m'] is None and main.analysis['feedback'] == []
