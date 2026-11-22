import pytest
import torch

from scripts.partial_field_loss import masked_corner_loss


def test_missing_landmarks_do_not_change_loss_or_gradient():
    prediction = torch.tensor([[0.5, 0.5, 1000.0, -1000.0]], requires_grad=True)
    target = torch.zeros_like(prediction)
    mask = torch.tensor([[1.0, 1.0, 0.0, 0.0]])
    loss = masked_corner_loss(prediction, target, mask)
    torch.testing.assert_close(loss, torch.tensor(0.125))
    loss.backward()
    torch.testing.assert_close(prediction.grad, torch.tensor([[0.25, 0.25, 0.0, 0.0]]))


def test_empty_mask_is_finite_and_shape_mismatch_rejected():
    value = torch.ones((1, 2))
    assert masked_corner_loss(value, value, torch.zeros_like(value)).item() == 0
    with pytest.raises(ValueError):
        masked_corner_loss(value, value, torch.ones((1, 1)))
