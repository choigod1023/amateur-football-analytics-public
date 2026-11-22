"""Background camera motion for pixel tracking, independent of pitch calibration."""
import math
import cv2
import numpy as np


def compensate_xyah(tracks, warp):
    """Warp XYAH centers/velocities without mixing aspect ratio with pixel height.

    BackgroundMotion estimates a similarity transform. Uniform zoom scales height
    and height velocity; aspect ratio remains invariant. Box dimensions are kept
    upright rather than enlarged repeatedly into rotated enclosing rectangles.
    """
    rotation = np.asarray(warp, float)[:, :2]
    scale = float(np.sqrt(abs(np.linalg.det(rotation))))
    transform = np.eye(8)
    transform[:2, :2] = rotation
    transform[4:6, 4:6] = rotation
    transform[3, 3] = transform[7, 7] = scale
    for track in tracks:
        track.mean = transform @ track.mean
        track.mean[:2] += warp[:, 2]
        track.covariance = transform @ track.covariance @ transform.T


class BackgroundMotion:
    method = 'background-lk'

    def __init__(self, downscale=2):
        self.downscale = downscale
        self.previous = None
        self.points = None
        self.counts = {'accepted': 0, 'rejected': 0, 'initialized': 0}
        self.last = {'state': 'uninitialized'}

    def reset_params(self):
        self.previous, self.points = None, None
        self.last = {'state': 'uninitialized'}

    def apply(self, frame, detections=None):
        h, w = frame.shape[:2]
        gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (w // self.downscale, h // self.downscale))
        mask = np.full(gray.shape, 255, np.uint8)
        # People must not define the camera transform.
        for b in ([] if detections is None else detections):
            x1, y1, x2, y2 = np.asarray(b[:4]) / self.downscale
            cv2.rectangle(mask, (max(0, int(x1) - 4), max(0, int(y1) - 4)),
                          (min(mask.shape[1] - 1, int(x2) + 4), min(mask.shape[0] - 1, int(y2) + 4)), 0, -1)
        new_points = cv2.goodFeaturesToTrack(gray, maxCorners=600, qualityLevel=.01, minDistance=8, mask=mask)
        warp = np.eye(2, 3, dtype=np.float64)
        state = 'initialized'
        count, ratio = 0, 0.
        if self.previous is not None and self.previous.shape == gray.shape and self.points is not None and len(self.points) >= 20:
            state = 'rejected'
            current, status, error = cv2.calcOpticalFlowPyrLK(self.previous, gray, self.points, None)
            if current is not None:
                back, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, self.previous, current, None)
                if back is not None:
                    p, q = self.points.reshape(-1, 2), current.reshape(-1, 2)
                    valid = status.ravel().astype(bool) & back_status.ravel().astype(bool)
                    valid &= np.linalg.norm(back.reshape(-1, 2) - p, axis=1) < 1.5
                    valid &= error.ravel() < 30
                    inside = (q[:, 0] >= 0) & (q[:, 0] < mask.shape[1]) & (q[:, 1] >= 0) & (q[:, 1] < mask.shape[0])
                    valid &= inside
                    selected = np.flatnonzero(valid)
                    selected = [i for i in selected if mask[int(q[i, 1]), int(q[i, 0])] != 0]
                    p, q = p[selected], q[selected]
                    if len(p) >= 20:
                        candidate, inliers = cv2.estimateAffinePartial2D(p, q, method=cv2.RANSAC, ransacReprojThreshold=2.)
                        if candidate is not None and inliers is not None:
                            good = inliers.ravel().astype(bool)
                            count, ratio = int(good.sum()), float(good.mean())
                            spread = np.ptp(p[good], axis=0) if count else np.zeros(2)
                            scale = np.linalg.norm(candidate[0, :2])
                            angle = abs(math.degrees(math.atan2(candidate[1, 0], candidate[0, 0])))
                            if (count >= 20 and ratio >= .6 and np.isfinite(candidate).all()
                                    and spread[0] >= .25 * gray.shape[1] and spread[1] >= .15 * gray.shape[0]
                                    and .9 <= scale <= 1.1 and angle <= 10
                                    and abs(candidate[0, 2]) <= .2 * gray.shape[1]
                                    and abs(candidate[1, 2]) <= .2 * gray.shape[0]):
                                warp = candidate
                                warp[:, 2] *= self.downscale
                                state = 'accepted'
        elif self.previous is not None:
            state = 'rejected'
        self.previous, self.points = gray, new_points
        self.counts[state] += 1
        self.last = {'state': state, 'inliers': count, 'inlier_ratio': ratio, 'warp': warp.tolist()}
        return warp


def tracker_config(fps):
    from ultralytics.utils import IterableSimpleNamespace
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('Tracking FPS must be positive')
    return IterableSimpleNamespace(track_high_thresh=.12, new_track_thresh=.12,
        track_low_thresh=.06, track_buffer=max(1, round(10 * fps)), match_thresh=.98, fuse_score=True)


def make_tracker(fps, camera_motion=False, legacy_camera=False, alignment_guard=False, camera_downscale=2):
    from ultralytics.trackers.byte_tracker import BYTETracker
    tracker = (BYTETracker if legacy_camera or not camera_motion else xyah_tracker_class(alignment_guard))(tracker_config(fps))
    if camera_motion:
        tracker.gmc = BackgroundMotion(downscale=camera_downscale)
    return tracker


def alignment_score(boxes, detections):
    """One-to-one IoU evidence, without ground-truth labels or track identities."""
    if not len(boxes) or not len(detections):
        return 0., 0
    a, b = np.asarray(boxes), np.asarray(detections)
    intersection = np.maximum(0, np.minimum(a[:, None, 2:], b[None, :, 2:]) - np.maximum(a[:, None, :2], b[None, :, :2])).prod(axis=2)
    union = (a[:, 2:]-a[:, :2]).prod(axis=1)[:, None] + (b[:, 2:]-b[:, :2]).prod(axis=1)[None, :] - intersection
    iou = intersection / np.maximum(union, 1e-9)
    ii, jj = np.where(iou > .1)
    pairs = [(float(iou[i, j]), int(i), int(j)) for i, j in zip(ii, jj)]
    left, right, total = set(), set(), 0.
    for value, i, j in sorted(pairs, reverse=True):
        if i not in left and j not in right:
            left.add(i); right.add(j); total += value
    return total / max(1, min(len(boxes), len(detections))), len(left)


def xyah_tracker_class(alignment_guard=False):
    from ultralytics.trackers.byte_tracker import BYTETracker

    class XYAHCameraTracker(BYTETracker):
        def _pre_first_associate(self, pool, unconfirmed, img, results_high):
            if img is not None and hasattr(self, 'gmc'):
                warp = self.gmc.apply(img, results_high.xyxy)
                if alignment_guard and pool:
                    boxes = np.array([track.xyxy for track in pool if self.frame_id - track.end_frame <= 2]).reshape(-1, 4)
                    centres = (boxes[:, :2] + boxes[:, 2:]) / 2
                    sizes = (boxes[:, 2:] - boxes[:, :2]) * np.sqrt(abs(np.linalg.det(warp[:, :2])))
                    centres = centres @ warp[:, :2].T + warp[:, 2]
                    projected = np.column_stack((centres - sizes / 2, centres + sizes / 2))
                    before, _ = alignment_score(boxes, results_high.xyxy)
                    after, count = alignment_score(projected, results_high.xyxy)
                    apply = after >= before + .01 and count >= 3
                    self.gmc.last.update({'association_before': before, 'association_after': after,
                                          'applied_to_tracks': apply})
                    if not apply:
                        warp = np.eye(2, 3)
                compensate_xyah(pool, warp)
                compensate_xyah(unconfirmed, warp)

    return XYAHCameraTracker


def cadence_steps(source_fps, tracking_fps, analysis_fps):
    if not all(math.isfinite(x) and x > 0 for x in (source_fps, tracking_fps, analysis_fps)):
        raise ValueError('Frame rates must be finite and positive')
    if tracking_fps < analysis_fps:
        raise ValueError('Tracking FPS cannot be lower than analysis FPS')
    analysis = max(1, round(source_fps / analysis_fps))
    tracking = max(1, round(source_fps / tracking_fps))
    # A common sampling grid keeps every existing analysis frame observable.
    if analysis % tracking:
        raise ValueError('Choose tracking FPS whose frame interval divides the analysis interval')
    return tracking, analysis
