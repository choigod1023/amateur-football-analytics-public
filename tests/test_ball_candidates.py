import torch
import pytest
from app.main import ball_candidates_from_boxes, validate_config


class Boxes:
    xyxy = torch.tensor([[10., 20., 30., 40.], [-5., -5., 5., 5.], [float('nan'), 0., 3., 4.], [90., 1., 80., 5.]])
    conf = torch.tensor([0.8, 0.6, 0.7, 0.7])


def test_ball_candidates_are_image_coordinates_and_invalid_boxes_are_skipped():
    assert ball_candidates_from_boxes(Boxes(), 100, 100) == [
        {'bbox_image_norm': [.1, .2, .3, .4], 'confidence': .8},
        {'bbox_image_norm': [0., 0., .05, .05], 'confidence': .6}]
    assert ball_candidates_from_boxes(None, 100, 100) == []
    assert ball_candidates_from_boxes(Boxes(), 0, 100) == []
    validate_config({'ball_detection': True})
    with pytest.raises(ValueError):
        validate_config({'ball_detection': 'true'})
