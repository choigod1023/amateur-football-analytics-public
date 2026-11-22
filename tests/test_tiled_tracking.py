import numpy as np
import pytest
import torch
from types import SimpleNamespace
from app.tiled_tracking import tile_windows, merge_boxes, TiledPlayerTracker, use_tiled_detection
from app.main import validate_config


def test_opt_in_auto_selects_once_from_aspect_ratio():
    validate_config({'tiled_detection': 'auto'})
    assert use_tiled_detection('auto', 6500, 1000)
    assert not use_tiled_detection('auto', 1920, 1080)
    assert not use_tiled_detection(False, 6500, 1000)
    assert use_tiled_detection(True, 1920, 1080)
    with pytest.raises(ValueError):
        validate_config({'tiled_detection': 'always'})


def test_tiles_cover_image_and_overlap_without_unbounded_work():
    for width, height in [(1, 1), (640, 1080), (6500, 1000), (100000, 20)] + [(w, h) for w in range(1, 600, 7) for h in (1, 2, 7, 23, 100)]:
        windows = tile_windows(width, height)
        assert windows[0][0] == 0 and windows[-1][1] == width
        assert all(a[1] >= b[0] for a, b in zip(windows, windows[1:]))
        assert len(windows) <= 12
    with pytest.raises(ValueError):
        tile_windows(0, 1)
    with pytest.raises(ValueError):
        validate_config({'tiled_detection': 1})


def test_merge_deduplicates_and_rejects_invalid_coordinates():
    values = [[10, 10, 30, 50, .9], [11, 11, 31, 51, .8],
              [-4, 20, 4, 30, .7], [5, 5, float('nan'), 6, .8], [4, 4, 3, 9, .9]]
    result = merge_boxes(values, 100, 100)
    assert result.shape == (2, 6)
    assert np.allclose(result[0], [10, 10, 30, 50, .9, 0])
    assert np.allclose(result[1], [0, 20, 4, 30, .7, 0])
    assert merge_boxes([], 100, 100).shape == (0, 6)
    assert len(merge_boxes([[i*2, 0, i*2+1, 1, .9] for i in range(1000)], 5000, 100)) == 300


def test_tracker_merges_tiles_before_tracking_and_resets_per_source():
    class Model:
        def __init__(self): self.calls = 0
        def predict(self, image, **kwargs):
            # Frame is 180 pixels wide, 100 high; windows begin at 0 and 80.
            # The same person appears as [85, 10, 95, 40] in both crops.
            index = self.calls % 2; self.calls += 1
            left = 0 if index == 0 else 80
            boxes = SimpleNamespace(xyxy=torch.tensor([[85-left,10.,95-left,40.]]), conf=torch.tensor([.9]))
            return [SimpleNamespace(boxes=boxes)]
    model = Model(); tracker = TiledPlayerTracker(model, 'cpu', 640, .35)
    frame = np.zeros((100, 180, 3), dtype=np.uint8)
    first = tracker.update(frame); second = tracker.update(frame)
    assert len(first) == len(second) == 1
    assert np.allclose(first[0][0], [85, 10, 95, 40], atol=1)
    assert first[0][1] == second[0][1]
    # Missing detections advance the same single tracker and do not manufacture a player.
    model.predict = lambda *a, **k: [SimpleNamespace(boxes=None)]
    assert tracker.update(frame) == []
