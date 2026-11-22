from types import SimpleNamespace

import numpy as np
import pytest
import torch

from app.ball_detection import ball_class_id, tile_windows, tiled_ball_candidates
from app.main import validate_config


def test_class_names_are_checked_without_assuming_coco_id():
    assert ball_class_id({0: 'person', 32: 'sports ball'}) == 32
    assert ball_class_id({0: 'ball'}) == 0
    assert ball_class_id({0: 'ball', 1: 'sports ball'}) is None
    assert ball_class_id({0: 'person'}) is None
    assert ball_class_id(None) is None
    validate_config({'ball_detection': True, 'ball_tiled_detection': True, 'ball_model_path':'ball.pt'})
    with pytest.raises(ValueError): validate_config({'ball_tiled_detection': 1})
    with pytest.raises(ValueError): validate_config({'ball_model_path': ''})


def test_windows_cover_frame_with_bounded_work():
    for width, height in ((1,1), (1280,720), (1920,1080), (6500,1000), (20000,10), (10,20000)):
        windows = tile_windows(width, height)
        assert len(windows) <= 24
        for x in np.linspace(0, width - 1, 25, dtype=int):
            for y in np.linspace(0, height - 1, 25, dtype=int):
                assert any(a <= x < c and b <= y < d for a, b, c, d in windows)
    with pytest.raises(ValueError): tile_windows(0, 4)


def test_tiled_predictions_are_reprojected_and_merged(monkeypatch):
    import app.ball_detection as module
    monkeypatch.setattr(module, 'tile_windows', lambda w,h: [(0,0,100,100), (80,0,180,100)])
    class Detector:
        def __init__(self): self.calls = 0
        def predict(self, image, **kwargs):
            left = (self.calls % 2) * 80
            self.calls += 1
            assert kwargs['classes'] == [0]
            return [SimpleNamespace(boxes=SimpleNamespace(
                xyxy=torch.tensor([[85.-left, 20., 95.-left, 30.]]), conf=torch.tensor([.9])))]
    result = tiled_ball_candidates(Detector(), np.zeros((100,180,3),np.uint8),
                                    class_id=0,device='cpu',image_size=640,confidence=.35)
    assert len(result) == 1
    assert result[0]['bbox_image_norm'] == [.47222,.2,.52778,.3]
    assert result[0]['confidence'] == .9
