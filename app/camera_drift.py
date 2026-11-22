"""Follow a small move of the camera and use it in the pitch calibration, instead of giving the run up.

The calibration clicks were made on a reference photo. A phone on a tripod drifts or is touched: this frame then shows the pitch a few pixels away from the photo. `CameraDriftTracker`
matches ORB features of the pitch part of the frame with the photo (partial affine transform with RANSAC, players move and are thrown out as outliers) and returns the translation
`shift = (dx, dy)` in pixels of the frame: how far the content of this frame lies from the same content in the photo. That is the `shift` argument of app.pitch_map.feet_to_metres.
Measured on this match (wiki/calibration-automation.md): cam1 stood still (< 0.3 px of 960), cam3 lay about (-7, +7) px (of 1920) off for the first 400 s of the second half.

States of `update`: 'ok' (a shift, medianed over the last measurements), 'moved' (the move is larger than `max_shift`, or the scale changed: a new calibration is needed, do not place players),
'unknown' (no start yet, or too few features or inliers for longer than `hold_seconds`; shorter gaps keep the last good shift and the state 'ok'). The caller must not place players in 'moved' or 'unknown'.
A median of 5 measurements keeps single bad fits (many players in the picture) out. Not measured: live use on a real stream, zoom changes, rolling shutter.
"""
import cv2
import numpy as np

WORK_WIDTH = 960


class CameraDriftTracker:
    def __init__(self, reference_image, pitch_top=0.5, max_shift=24.0, max_scale=0.02, period=5.0, hold_seconds=10.0, history=5, min_inliers=12):
        """reference_image: BGR photo of the calibration. pitch_top: fraction of the height above which is stands and sky (left out). max_shift: pixels of the full frame."""
        self.orb = cv2.ORB_create(nfeatures=1800)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.shape = reference_image.shape[:2]
        self.ratio = min(1.0, WORK_WIDTH / self.shape[1])
        self.pitch_top, self.max_shift, self.max_scale = pitch_top, max_shift, max_scale
        self.period, self.hold_seconds, self.history, self.min_inliers = period, hold_seconds, history, min_inliers
        self.points, self.descriptors = self._features(reference_image)
        self.shifts = []
        self.state = 'unknown'
        self.shift = (0.0, 0.0)
        self.last_good = None
        self.last_try = None

    def _features(self, image):
        small = cv2.resize(image, None, fx=self.ratio, fy=self.ratio) if self.ratio != 1.0 else image
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        mask = np.zeros(gray.shape, np.uint8)
        mask[int(gray.shape[0] * self.pitch_top):, :] = 255
        return self.orb.detectAndCompute(gray, mask)

    @property
    def usable(self):
        return self.descriptors is not None and len(self.points) >= self.min_inliers

    def measure(self, frame):
        """(dx, dy, scale_change) of this frame against the photo in full-frame pixels, or None when there is not enough evidence."""
        if not self.usable or frame is None or frame.shape[:2] != self.shape:
            return None
        points, descriptors = self._features(frame)
        if descriptors is None or len(points) < self.min_inliers:
            return None
        matches = self.matcher.knnMatch(self.descriptors, descriptors, k=2)
        good = [pair[0] for pair in matches if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance]
        if len(good) < self.min_inliers:
            return None
        src = np.float32([self.points[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([points[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.0, maxIters=2000, confidence=0.99)
        if matrix is None or inliers is None:
            return None
        selected = inliers.ravel().astype(bool)
        if selected.sum() < self.min_inliers or selected.mean() < 0.4:
            return None
        scale = float(np.hypot(matrix[0, 0], matrix[1, 0]))
        centre = np.array([[[self.shape[1] * self.ratio / 2, self.shape[0] * self.ratio * (1 + self.pitch_top) / 2]]], np.float32)        # the middle of the pitch part, where players stand
        moved = cv2.transform(centre, matrix).reshape(2) - centre.reshape(2)
        return float(moved[0] / self.ratio), float(moved[1] / self.ratio), scale - 1.0

    def update(self, frame, t):
        """Measure at most every `period` seconds. Returns the state: 'ok', 'moved' or 'unknown'; `shift` holds the shift to use when the state is 'ok'."""
        if self.last_try is not None and t - self.last_try < self.period and self.state != 'unknown':
            return self.state
        self.last_try = t
        try:
            result = self.measure(frame)
        except cv2.error:
            result = None
        if result is None:
            if self.last_good is not None and t - self.last_good <= self.hold_seconds:
                self.state = 'ok'                                              # a short gap: the last shift stays
            else:
                self.state = 'unknown'                                         # too long without evidence: the caller must not place players
            return self.state
        dx, dy, scale = result
        if (dx * dx + dy * dy) ** 0.5 > self.max_shift or abs(scale) > self.max_scale:
            self.state, self.shifts = 'moved', []
            return self.state
        self.shifts.append((dx, dy))
        del self.shifts[:-self.history]
        self.shift = (float(np.median([s[0] for s in self.shifts])), float(np.median([s[1] for s in self.shifts])))
        self.last_good = t
        self.state = 'ok'
        return self.state
