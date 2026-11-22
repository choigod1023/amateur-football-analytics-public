"""Colour and shape features of one person box, for a small team and role classifier.

The features describe the upper body of a box (hue histogram weighted by saturation, neon, dark and pale shares,
mean colour) and the box geometry. They carry no pitch calibration. The neon range is the one used for the yellow
vests of this particular match; another match needs its own labels.
"""
import cv2
import numpy as np

CLASSES = ('referee', 'spectator', 'team_a', 'team_b')
FEATURE_NAMES = tuple(f'hue_{i}' for i in range(12)) + ('neon', 'dark', 'pale', 'saturation', 'value', 'height', 'aspect',
                                                       'feet_y', 'centre_x', 'blue', 'green', 'red')


def class_of(role, team_group):
    """Training class of a human label, or None when the label is not usable (duplicate, unknown, shadow ...)."""
    if role == 'referee':
        return 'referee'
    if role == 'spectator':
        return 'spectator'
    if role in ('player', 'goalkeeper') and team_group in ('team_a', 'team_b'):
        return team_group
    return None


def box_features(image, bbox_norm):
    """image: BGR array; bbox_norm: [x1, y1, x2, y2] as fractions of the image. Returns a float32 vector."""
    height, width = image.shape[:2]
    x1, y1, x2, y2 = bbox_norm
    left, top, right, bottom = int(x1 * width), int(y1 * height), int(x2 * width), int(y2 * height)
    box_h, box_w = max(2, bottom - top), max(2, right - left)
    patch = image[top + int(.15 * box_h):top + int(.6 * box_h) + 1, left + int(.2 * box_w):right - int(.2 * box_w) + 1]
    if patch.size == 0:
        patch = image[top:bottom, left:right]
    if patch.size == 0:
        return np.zeros(len(FEATURE_NAMES), np.float32)
    patch = cv2.resize(patch, (12, 16), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    hue = np.histogram(hsv[:, 0], bins=12, range=(0, 180), weights=hsv[:, 1] / 255)[0] / len(hsv)
    neon = ((hsv[:, 0] >= 22) & (hsv[:, 0] <= 44) & (hsv[:, 1] > 90) & (hsv[:, 2] > 110)).mean()
    dark = (hsv[:, 2] < 70).mean()
    pale = ((hsv[:, 1] < 40) & (hsv[:, 2] > 150)).mean()
    blue, green, red = patch.reshape(-1, 3).astype(np.float32).mean(0) / 255
    return np.concatenate([hue, [neon, dark, pale, hsv[:, 1].mean() / 255, hsv[:, 2].mean() / 255, box_h / height * 5,
                                 box_w / box_h, y2, (x1 + x2) / 2, blue, green, red]]).astype(np.float32)
