import json
import subprocess
import sys

import cv2
import numpy as np
import pytest

from scripts.prepare_calibration_config import prepare


def data():
    return {'image_size_px': [1000, 500], 'field_size_m': [100, 50],
            'fitting_points': [
                {'image_point': [100, 50], 'field_point_m': [0, 0]},
                {'image_point': [900, 50], 'field_point_m': [100, 0]},
                {'image_point': [900, 450], 'field_point_m': [100, 50]},
                {'image_point': [100, 450], 'field_point_m': [0, 50]}],
            'checkpoints': [
                {'image_point': [300, 150], 'field_point_m': [25, 12.5]},
                {'image_point': [500, 250], 'field_point_m': [50, 25]},
                {'image_point': [700, 350], 'field_point_m': [75, 37.5]}]}


def reference(tmp_path):
    p = tmp_path / 'frame.png'
    assert cv2.imwrite(str(p), np.zeros((500, 1000, 3), dtype=np.uint8))
    return p


def test_candidate_is_inactive_and_preserves_team_flags(tmp_path):
    base = {'own_team': 'away', 'team_classification_validated': False}
    result = prepare(base, data(), reference(tmp_path))
    assert result['config']['calibration']['validated'] is False
    assert result['independent_checkpoint_report']['measured'] == 3
    assert result['config']['team_classification_validated'] is False
    assert 'calibration' not in base


def test_activation_requires_explicit_tolerance_and_independent_points(tmp_path):
    ref = reference(tmp_path)
    with pytest.raises(ValueError):
        prepare({}, data(), ref, accept_measured=True)
    measurements = data(); measurements['checkpoints'] = measurements['checkpoints'][:2]
    with pytest.raises(ValueError):
        prepare({}, measurements, ref, accept_measured=True, max_error_m=1)
    measurements = data(); measurements['checkpoints'][0]['field_point_m'] = [45, 12.5]
    with pytest.raises(ValueError):
        prepare({}, measurements, ref, accept_measured=True, max_error_m=1)
    measurements = data(); measurements['checkpoints'][0]['field_point_m'] = [25.5004, 12.5]
    with pytest.raises(ValueError):
        prepare({}, measurements, ref, accept_measured=True, max_error_m=.5)
    result = prepare({}, data(), ref, accept_measured=True, max_error_m=1)
    assert result['config']['calibration']['validated'] is True
    assert result['config']['calibration']['camera_guard_reference'] == str(ref.resolve())


def test_reference_resolution_and_existing_file_are_rejected(tmp_path):
    bad = tmp_path / 'wrong.png'
    assert cv2.imwrite(str(bad), np.zeros((100, 100, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        prepare({}, data(), bad)
    ref = reference(tmp_path)
    base = tmp_path / 'base.json'; base.write_text('{}', encoding='utf8')
    measured = tmp_path / 'measurements.json'; measured.write_text(json.dumps(data()), encoding='utf8')
    out = tmp_path / 'config.json'; out.write_text('do not overwrite', encoding='utf8')
    script = 'scripts/prepare_calibration_config.py'
    proc = subprocess.run([sys.executable, script, '--base', str(base), '--measurements', str(measured),
                           '--reference', str(ref), '--output', str(out)], capture_output=True, text=True)
    assert proc.returncode != 0
    assert out.read_text(encoding='utf8') == 'do not overwrite'


def test_feature_region_does_not_change_projection_area(tmp_path):
    ref = reference(tmp_path); measurements = data()
    measurements['camera_guard_feature_region'] = [[0, 0], [999, 0], [999, 499], [0, 499]]
    result = prepare({}, measurements, ref)
    cal = result['config']['calibration']
    assert cal['camera_guard_feature_region'] != cal['image_points']
    measurements['camera_guard_feature_region'][0] = [-1, 0]
    with pytest.raises(ValueError):
        prepare({}, measurements, ref)
