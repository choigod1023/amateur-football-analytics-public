import numpy as np

from scripts.evaluate_green_temporal import median_candidate


def test_median_ignores_missing_candidates_without_fabricating_them():
    base = np.arange(8).reshape(4, 2)
    assert median_candidate([base, None, base + 2]) is None
    np.testing.assert_array_equal(median_candidate([base, None, base + 1, base + 100]), base + 1)


def test_median_rejects_bad_geometry_and_nonfinite_values():
    valid = np.zeros((4, 2))
    assert median_candidate([valid, valid, np.zeros((3, 2))]) is None
    assert median_candidate([valid, valid, np.full((4, 2), np.nan)]) is None
