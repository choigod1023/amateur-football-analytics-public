"""Conservative per-frame camera movement check, not calibration verification.

An ORB correspondence majority and a robust affine fit compare the current
frame with a separately supplied calibration reference. Failure to find enough
evidence is an abstention. An affine fit cannot prove a fixed camera or detect
every movement, rolling shutter, lens or moving-background failure.
"""
from pathlib import Path
import cv2
import numpy as np


class CameraMotionGuard:
    def __init__(self, reference_path, image_points):
        self.orb = cv2.ORB_create(nfeatures=1800)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.reference = None
        self.ref_shape = None
        self.ref_descriptors = None
        self.ref_points = None
        try:
            image = cv2.imread(str(Path(reference_path)), cv2.IMREAD_COLOR)
            if image is None or not image.size:
                return
            h, w = image.shape[:2]
            self.ref_shape = (h, w)
            self.ratio = min(1.0, 960.0 / w)
            self.size = (max(1, round(w*self.ratio)), max(1, round(h*self.ratio)))
            gray = cv2.cvtColor(cv2.resize(image, self.size), cv2.COLOR_BGR2GRAY)
            polygon = np.asarray(image_points, dtype=float)
            if polygon.shape != (4, 2) or not np.isfinite(polygon).all():
                return
            polygon = np.round(polygon * self.ratio).astype(np.int32)
            mask = np.zeros(gray.shape, np.uint8)
            cv2.fillConvexPoly(mask, polygon, 255)
            points, descriptors = self.orb.detectAndCompute(gray, mask)
            if descriptors is None or len(points) < 12:
                return
            self.ref_points, self.ref_descriptors = points, descriptors
            self.reference = True
        except (TypeError, ValueError, OSError, cv2.error):
            return

    def check(self, frame):
        if self.reference is None:
            return 'camera_reference_unavailable'
        if frame is None or frame.shape[:2] != self.ref_shape:
            return 'camera_guard_insufficient'
        try:
            gray = cv2.cvtColor(cv2.resize(frame, self.size), cv2.COLOR_BGR2GRAY)
            points, desc = self.orb.detectAndCompute(gray, None)
            if desc is None or len(points) < 12:
                return 'camera_guard_insufficient'
            matches = self.matcher.knnMatch(self.ref_descriptors, desc, k=2)
            good = [pair[0] for pair in matches if len(pair) == 2 and pair[0].distance < .75 * pair[1].distance]
            if len(good) < 12:
                return 'camera_guard_insufficient'
            src = np.float32([self.ref_points[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst = np.float32([points[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                ransacReprojThreshold=2.0, maxIters=2000, confidence=.99)
            if matrix is None or inliers is None:
                return 'camera_guard_insufficient'
            selected = inliers.ravel().astype(bool)
            if selected.sum() < 12 or selected.mean() < .5:
                return 'camera_guard_insufficient'
            projected = cv2.transform(src[selected], matrix).reshape(-1, 2)
            displacement = np.linalg.norm(projected - src[selected].reshape(-1, 2), axis=1)
            # Express the screen displacement as a fraction of its width; no
            # geometric accuracy in metres can be inferred from this threshold.
            if float(np.percentile(displacement, 90)) > .003 * self.size[0]:
                return 'camera_moved'
            return 'stable'
        except (cv2.error, ValueError, TypeError):
            return 'camera_guard_insufficient'
