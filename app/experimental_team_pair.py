"""Opt-in research-only team matching. Not connected to the live server.

The caller must establish that a crop belongs to an outfield player; this
model cannot distinguish referees, goalkeepers, crowds, or track switches.
"""
import cv2
import numpy as np


def shirt_histogram(frame, box):
    x1, y1, x2, y2 = map(int, box)
    h, w = frame.shape[:2]
    if x1 < 0 or y1 < 0 or x2 > w or y2 > h or x2-x1 < 12 or y2-y1 < 30:
        return None
    bw, bh = x2-x1, y2-y1
    crop = frame[y1+int(bh*.15):y1+int(bh*.55), x1+int(bw*.15):x1+int(bw*.85)]
    if not crop.size:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    hsv = hsv[(hsv[:, 2] > 40) & ~((hsv[:, 0] > 35) & (hsv[:, 0] < 85) & (hsv[:, 1] > 70))]
    if len(hsv) < 30:
        return None
    colored, grey = hsv[hsv[:, 1] >= 65], hsv[hsv[:, 1] < 65]
    hist = np.zeros(16, dtype=np.float32)
    hist[:12] = np.histogram(colored[:, 0], bins=12, range=(0, 180))[0]
    hist[12:] = np.histogram(grey[:, 2], bins=4, range=(0, 256))[0]
    hist /= max(hist.sum(), 1)
    return hist


class ExperimentalTeamPair:
    def __init__(self, weights, support):
        self.w1 = np.asarray(weights['weights1'], dtype=np.float32)
        self.b1 = np.asarray(weights['bias1'], dtype=np.float32)
        self.w2 = np.asarray(weights['weights2'], dtype=np.float32)
        self.b2 = np.asarray(weights['bias2'], dtype=np.float32)
        self.margin, self.floor = float(weights['margin']), float(weights['floor'])
        self.support = {team: np.asarray(support[team], dtype=np.float32) for team in ('home', 'away')}
        if (self.w1.shape != (32, 16) or self.b1.shape != (32,) or self.w2.shape != (1, 32)
                or self.b2.shape != (1,) or not (0 <= self.margin <= 1 and 0 <= self.floor <= 1)
                or any(v.ndim != 2 or v.shape[1] != 16 or len(v) < 3 or len(v) > 100 for v in self.support.values())
                or not all(np.isfinite(v).all() for v in (self.w1, self.b1, self.w2, self.b2, *self.support.values()))):
            raise ValueError('Invalid team pair weights or labeled support')

    def classify(self, frame, box, *, role=None):
        # The existing detector predicts persons, not outfield-player roles.
        if role != 'player':
            return 'unknown'
        hist = shirt_histogram(frame, box)
        if hist is None:
            return 'unknown'
        scores = []
        for team in ('home', 'away'):
            features = np.abs(self.support[team] - hist)
            hidden = np.maximum(features @ self.w1.T + self.b1, 0)
            logits = (hidden @ self.w2.T + self.b2).ravel()
            p = 1 / (1 + np.exp(-np.clip(logits, -80, 80)))
            scores.append(float(np.mean(np.sort(p)[-3:])))
        if max(scores) < self.floor or abs(scores[0]-scores[1]) < self.margin:
            return 'unknown'
        return 'home' if scores[0] > scores[1] else 'away'
