import numpy as np

from scripts.audit_wide_size_thresholds import score_frame, size_bin


def test_size_bins_are_half_open():
    assert size_bin([0, 0, 10, 39]) == 'under_40px'
    assert size_bin([0, 0, 10, 40]) == '40_to_79px'
    assert size_bin([0, 0, 10, 80]) == '80px_plus'


def test_score_uses_same_threshold_for_boxes_and_size_matches():
    ground = [('a', [0, 0, 10, 30]), ('b', [20, 0, 30, 100])]
    boxes = np.array([[0, 0, 10, 30, .4, 0], [20, 0, 30, 100, .9, 0]])
    scored = score_frame(ground, boxes, .5)
    assert scored == {'predicted': 1, 'matched': 1, 'groups': {
        'under_40px': {'gt': 1, 'matched': 0},
        '80px_plus': {'gt': 1, 'matched': 1},
    }}
