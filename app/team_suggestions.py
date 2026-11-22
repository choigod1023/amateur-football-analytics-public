"""Unverified shirt-colour groups for optional live candidate display.

Group numbers have no home/away or role meaning; referees may be grouped.
Never use these suggestions for tactical measurements without confirmation.
"""
import cv2
import numpy as np


def shirt_histogram(frame, box):
    x1, y1, x2, y2 = map(int, box)
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
    w, h = x2-x1, y2-y1
    if w < 12 or h < 30:
        return None
    crop = frame[y1+int(h*.15):y1+int(h*.55), x1+int(w*.15):x1+int(w*.85)]
    if not crop.size:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    hsv = hsv[(hsv[:, 2] > 40) & ~((hsv[:, 0] > 35) & (hsv[:, 0] < 85) & (hsv[:, 1] > 70))]
    if len(hsv) < 30:
        return None
    colour, grey = hsv[hsv[:, 1] >= 65], hsv[hsv[:, 1] < 65]
    out = np.zeros(16, dtype=np.float32)
    if len(colour): out[:12] = np.histogram(colour[:, 0], 12, (0, 180))[0]
    if len(grey): out[12:] = np.histogram(grey[:, 2], 4, (0, 256))[0]
    return out / max(float(out.sum()), 1.)


class TeamSuggestions:
    """Fit once from early, *unlabelled* tracks; never infer home/away."""
    def __init__(self, frames=10, margin=.15, separation=.20, max_distance=.4):
        self.frames, self.margin, self.separation = frames, margin, separation
        self.max_distance = max_distance
        self.seen_frames = 0
        self.samples = {}
        self.centres = None

    def update(self, frame, tracks):
        feats = {str(track_id): shirt_histogram(frame, box) for box, track_id in tracks}
        if self.centres is None:
            for tid, feature in feats.items():
                if feature is not None and (tid in self.samples or len(self.samples) < 200):
                    self.samples.setdefault(tid, []).append(feature)
            self.seen_frames += 1
            if self.seen_frames == self.frames:
                self._fit()
                self.seen_frames = 0
            return {tid: None for tid in feats}
        return {tid: self._classify(feature) for tid, feature in feats.items()}

    def _fit(self):
        tracks = [np.median(np.stack(values), axis=0) for values in self.samples.values() if values]
        self.samples.clear()
        if len(tracks) < 4:
            return
        x = np.asarray(tracks, dtype=np.float32)
        distance = np.sum((x[:, None, :] - x[None, :, :])**2, axis=2)
        i, j = np.unravel_index(np.argmax(distance), distance.shape)
        centres = np.stack((x[i], x[j]))
        for _ in range(20):
            groups = np.argmin(np.linalg.norm(x[:, None, :] - centres[None, :, :], axis=2), axis=1)
            if min(np.bincount(groups, minlength=2)) < 2:
                return
            new = np.stack([x[groups == group].mean(axis=0) for group in (0, 1)])
            if np.allclose(new, centres, atol=1e-5):
                break
            centres = new
        if np.linalg.norm(centres[0]-centres[1]) >= self.separation:
            self.centres = centres

    def _classify(self, feature):
        if self.centres is None or feature is None:
            return None
        distances = np.linalg.norm(self.centres-feature[None, :], axis=1)
        if float(distances.min()) > self.max_distance:
            return None
        scale = max(float(distances.max()), 1e-9)
        if (float(distances.max())-float(distances.min())) / scale < self.margin:
            return None
        return int(np.argmin(distances))
