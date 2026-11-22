"""Conservative human-selected shirt reference sampling in OpenCV HSV.

This estimates colours, not player roles, team identity or classification accuracy.
"""
import cv2
import numpy as np


def sample_shirt(frame, rect):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('Expected an 8-bit BGR frame')
    if not isinstance(rect, (list, tuple)) or len(rect) != 4 or any(type(v) is not int for v in rect):
        raise ValueError('Shirt rectangle must be four integer pixels')
    x1, y1, x2, y2 = rect
    height, width = frame.shape[:2]
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height) or x2-x1 < 3 or y2-y1 < 3:
        raise ValueError('Shirt rectangle must fit inside the frame and be at least 3 by 3 pixels')
    hsv = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(float)
    pixels = hsv[hsv[:, 2] > 45]
    if len(pixels) < max(9, int(np.ceil(len(hsv)*.8))):
        raise ValueError('Shirt area is too dark or obscured')
    s, v = np.median(pixels[:, 1:], axis=0)
    if np.median(np.abs(pixels[:, 1] - s)) > 35 or np.median(np.abs(pixels[:, 2] - v)) > 35:
        raise ValueError('Shirt area has mixed colours or lighting')
    if s <= 55:
        if np.mean(pixels[:, 1] <= 55) < .8:
            raise ValueError('Shirt area mixes grey and saturated colours')
        return [0, int(round(s)), int(round(v))]
    if s < 70 or np.mean(pixels[:, 1] >= 55) < .8:
        raise ValueError('Shirt saturation is ambiguous')
    angle = pixels[:, 0] * (2*np.pi/180)
    vector = np.mean(np.exp(1j*angle))
    if abs(vector) < .9:
        raise ValueError('Shirt area contains inconsistent hues')
    hue = (np.angle(vector) % (2*np.pi)) * 180/(2*np.pi)
    return [int(round(hue)) % 180, int(round(s)), int(round(v))]


def build_references(frame, home_rect, away_rect):
    refs = {'home': sample_shirt(frame, home_rect), 'away': sample_shirt(frame, away_rect)}
    a, b = (np.asarray(refs[t], dtype=float) for t in ('home', 'away'))
    dh = min(abs(a[0]-b[0]), 180-abs(a[0]-b[0]))
    hue_weight = min(a[1], b[1])/255
    separation = np.sqrt((dh*2*hue_weight)**2 + ((a[1]-b[1])*.30)**2 + ((a[2]-b[2])*.25)**2)
    if separation < 25:
        raise ValueError('Team shirt references are too similar to separate reliably')
    return {'team_hsv': refs, 'team_classification_validated': False}
