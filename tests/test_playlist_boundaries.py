import pytest
from scripts.playlist_boundaries import reset_required


def test_reset_only_on_missing_segment_or_loop():
    assert not reset_required(0, 1)
    assert not reset_required(1, 2)
    assert reset_required(2, 3)
    assert reset_required(3, 4)
    assert not reset_required(4, 5)
    assert reset_required(1, 5)  # a missed progress update can cross a cut
    assert reset_required(8, 0)  # restarted PTS timeline


def test_invalid_segment_is_rejected():
    with pytest.raises(ValueError): reset_required(-1, 2)
    with pytest.raises(ValueError): reset_required(0, True)
