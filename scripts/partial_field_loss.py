"""Loss for landmarks where unobserved coordinates carry no supervision."""
import torch.nn.functional as F


def masked_corner_loss(prediction, target, mask):
    if prediction.shape != target.shape or target.shape != mask.shape:
        raise ValueError("prediction, target and mask must have identical shapes")
    per_coordinate = F.smooth_l1_loss(prediction, target, reduction="none")
    return (per_coordinate * mask).sum() / mask.sum().clamp_min(1)
