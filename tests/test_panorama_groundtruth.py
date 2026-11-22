import numpy as np
import pytest

from app.main import validate_config
from scripts.experimental_panorama_groundtruth import evaluate, make_candidate
from scripts.experimental_green_pitch import propose


def test_candidate_is_inactive_and_uses_ordered_matching_corners():
    pairs = [(np.array(image, float), np.array(field, float)) for image, field in [
        ([0, 0], [0, 0]), ([100, 0], [105, 0]), ([100, 100], [105, 68]),
        ([0, 100], [0, 68]), ([50, 50], [52.5, 34])]]
    candidate = make_candidate(pairs)
    assert candidate['validated'] is False
    validate_config({'calibration':candidate})
    result = evaluate(pairs)
    assert result['runtime_guarded_four_corners']['returned'] == 1
    assert result['runtime_guarded_four_corners']['median_m'] < 0.001


def test_candidate_rejects_missing_corners():
    with pytest.raises(ValueError):
        make_candidate([(np.array([0.,0.]),np.array([0.,0.]))])


def test_green_detector_abstains_for_blank_image():
    assert propose(np.zeros((1000,6500,3),dtype=np.uint8)) is None
