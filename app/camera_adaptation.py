"""Conservative same-pitch registration, not automatic landmark recognition.

Only features inside a supplied planar pitch polygon are used. A first fit
locates that polygon in the new image; a second, masked fit is validated on
held-out correspondences. Reprojection pixels are not field-position metres.
Parallax, repetitive markings, people and changed light can defeat registration;
failure returns no transform and asks for landmark confirmation.
"""
import cv2
import numpy as np


def _project(points, matrix):
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homogeneous = np.column_stack((points, np.ones(len(points)))) @ matrix.T
    if not np.isfinite(homogeneous).all() or np.any(np.abs(homogeneous[:, 2]) < 1e-8):
        return None
    if not (np.all(homogeneous[:, 2] > 0) or np.all(homogeneous[:, 2] < 0)):
        return None
    return homogeneous[:, :2] / homogeneous[:, 2, None]


def _area(points):
    return abs(float(cv2.contourArea(np.asarray(points, np.float32))))


def _mask(shape, polygon):
    mask = np.zeros(shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, np.rint(polygon).astype(np.int32), 255)
    return mask


class CameraAdaptation:
    def __init__(self, max_width=1280, min_matches=24, minimum_coverage=.12,
                 max_holdout_median_px=2.5, max_holdout_p90_px=5.0, method='orb'):
        self.max_width = max_width
        self.min_matches = min_matches
        self.minimum_coverage = minimum_coverage
        self.max_holdout_median_px = max_holdout_median_px
        self.max_holdout_p90_px = max_holdout_p90_px
        if method not in ('orb', 'sift'):
            raise ValueError('Feature method must be orb or sift')
        self.method = method
        self.orb = (cv2.ORB_create(nfeatures=5000, fastThreshold=10) if method == 'orb'
                    else cv2.SIFT_create(nfeatures=5000))
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING if method == 'orb' else cv2.NORM_L2)

    @staticmethod
    def _review(reason, **evidence):
        return {'status': 'needs_review', 'reason': reason, 'current_to_reference': None,
                'reference_to_current': None, 'human_action': 'Confirm at least four well-spread pitch landmarks in the current frame.',
                'metric_accuracy_verified': False, **evidence}

    def _prepare(self, image):
        h, w = image.shape[:2]
        scale = min(1., self.max_width / w)
        size = (round(w * scale), round(h * scale))
        gray = cv2.cvtColor(cv2.resize(image, size), cv2.COLOR_BGR2GRAY)
        return gray, scale

    def _matches(self, ref, current, ref_mask, current_mask, sr, sc):
        rk, rd = self.orb.detectAndCompute(ref, ref_mask)
        ck, cd = self.orb.detectAndCompute(current, current_mask)
        if rd is None or cd is None or len(rk) < self.min_matches or len(ck) < self.min_matches:
            return None
        forward = self.matcher.knnMatch(rd, cd, k=2)
        backward = self.matcher.knnMatch(cd, rd, k=2)
        reverse = {m[0].queryIdx: m[0].trainIdx for m in backward if len(m) == 2 and m[0].distance < .72 * m[1].distance}
        good = [m[0] for m in forward if len(m) == 2 and m[0].distance < .72 * m[1].distance
                and reverse.get(m[0].trainIdx) == m[0].queryIdx]
        if len(good) < self.min_matches:
            return None
        return (np.float32([rk[m.queryIdx].pt for m in good]) / sr,
                np.float32([ck[m.trainIdx].pt for m in good]) / sc)

    @staticmethod
    def _geometry(matrix, polygon, current_shape, reference_shape=None):
        if matrix is None or matrix.shape != (3, 3) or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-10:
            return None
        mapped = _project(polygon, matrix)
        if mapped is None or not cv2.isContourConvex(np.float32(mapped)):
            return None
        # Reject mirrored fields, folded projective planes, extreme extrapolation.
        if cv2.contourArea(np.float32(mapped), oriented=True) * cv2.contourArea(np.float32(polygon), oriented=True) <= 0:
            return None
        resolution_ratio = (current_shape[0] * current_shape[1] /
                            (reference_shape[0] * reference_shape[1])) if reference_shape else 1.
        if not .35 <= _area(mapped) / max(_area(polygon), 1.) / resolution_ratio <= 3.0:
            return None
        h, w = current_shape[:2]
        image_rect = np.float32([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]])
        visible, _ = cv2.intersectConvexConvex(np.float32(mapped), image_rect)
        if visible / max(_area(mapped), 1.) < .60:
            return None
        return mapped

    def fit(self, reference_bgr, current_bgr, polygon_px):
        """Return ready + pixel homographies or needs_review + no homography.

        polygon_px is an ordered, convex ground-plane polygon in the reference
        image. Never include stands, fence, sky or people as calibration support.
        This function does not cache an old transform across failures.
        """
        try:
            if (reference_bgr is None or current_bgr is None or reference_bgr.ndim != 3 or current_bgr.ndim != 3
                    or min(reference_bgr.shape[:2]) < 32 or min(current_bgr.shape[:2]) < 32):
                return self._review('invalid_frame')
            polygon = np.asarray(polygon_px, dtype=np.float32)
            if (polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 4 or not np.isfinite(polygon).all()
                    or not cv2.isContourConvex(polygon) or _area(polygon) < 400):
                return self._review('invalid_pitch_polygon')
            rh, rw = reference_bgr.shape[:2]
            if np.any(polygon < 0) or np.any(polygon[:, 0] >= rw) or np.any(polygon[:, 1] >= rh):
                return self._review('pitch_polygon_outside_reference')
            ref, sr = self._prepare(reference_bgr)
            current, sc = self._prepare(current_bgr)
            ref_mask = _mask(ref.shape, polygon * sr)
            pairs = self._matches(ref, current, ref_mask, None, sr, sc)
            if pairs is None:
                return self._review('insufficient_pitch_matches')
            preliminary, _ = cv2.findHomography(*pairs, cv2.RANSAC, 3.0)
            moved_polygon = self._geometry(preliminary, polygon, current_bgr.shape, reference_bgr.shape)
            if moved_polygon is None:
                return self._review('unsafe_initial_geometry')
            pairs = self._matches(ref, current, ref_mask, _mask(current.shape, moved_polygon * sc), sr, sc)
            if pairs is None:
                return self._review('insufficient_masked_matches')
            source, target = pairs
            # Spatially interleaved deterministic heldout matches are not used
            # in the returned fit. They are correspondence checks, not human GT.
            order = np.lexsort((source[:, 1], source[:, 0]))
            heldout = order[::5]
            train = np.setdiff1d(order, heldout)
            matrix, inliers = cv2.findHomography(source[train], target[train], cv2.RANSAC, 3.0)
            mapped_polygon = self._geometry(matrix, polygon, current_bgr.shape, reference_bgr.shape)
            if mapped_polygon is None or inliers is None:
                return self._review('unsafe_geometry')
            selected = inliers.ravel().astype(bool)
            inlier_count = int(selected.sum())
            if inlier_count < 16 or selected.mean() < .65:
                return self._review('weak_consensus', matches=len(source), inliers=inlier_count)
            support = source[train][selected]
            coverage = _area(cv2.convexHull(support).reshape(-1, 2)) / _area(polygon)
            target_support = target[train][selected]
            target_coverage = _area(cv2.convexHull(target_support).reshape(-1, 2)) / _area(mapped_polygon)
            if min(coverage, target_coverage) < self.minimum_coverage:
                return self._review('localized_support', coverage=float(coverage), current_coverage=float(target_coverage))
            predicted = _project(source[heldout], matrix)
            if predicted is None:
                return self._review('invalid_holdout_projection')
            errors = np.linalg.norm(predicted - target[heldout], axis=1)
            med, p90 = float(np.median(errors)), float(np.percentile(errors, 90))
            if med > self.max_holdout_median_px or p90 > self.max_holdout_p90_px:
                return self._review('holdout_disagreement', holdout_median_px=med, holdout_p90_px=p90)
            inverse = np.linalg.inv(matrix)
            # Homographies may validly have h33=0. Preserve a positive
            # homogeneous denominator on the supported ground plane instead
            # of dividing by h33 (pitch_map.apply rejects negative depth).
            matrix /= np.linalg.norm(matrix)
            inverse /= np.linalg.norm(inverse)
            if np.mean(np.column_stack((polygon, np.ones(len(polygon)))) @ matrix[2]) < 0:
                matrix = -matrix
            if np.mean(np.column_stack((mapped_polygon, np.ones(len(mapped_polygon)))) @ inverse[2]) < 0:
                inverse = -inverse
            return {'status': 'ready', 'reason': 'validated_pitch_correspondences',
                    'feature_method': self.method,
                    'current_to_reference': inverse.tolist(), 'reference_to_current': matrix.tolist(),
                    'reference_size': [rw, rh], 'current_size': [current_bgr.shape[1], current_bgr.shape[0]],
                    'support_polygon_current': mapped_polygon.tolist(), 'matches': len(source),
                    'inliers': inlier_count, 'coverage': float(coverage), 'current_coverage': float(target_coverage),
                    'holdout_count': len(heldout), 'holdout_median_px': med, 'holdout_p90_px': p90,
                    'metric_accuracy_verified': False, 'human_action': None}
        except (cv2.error, ValueError, TypeError, IndexError, np.linalg.LinAlgError):
            return self._review('registration_failed')


def transfer_calibration(fitted, registration):
    """Compose normalized-reference→metres with current-pixel→reference-pixel.

    Return a new fitted mapping for normalized current coordinates. Never fall
    back to the old mapping when registration abstains.
    """
    if registration.get('status') != 'ready' or registration.get('current_to_reference') is None:
        raise ValueError('Camera registration requires human review')
    rw, rh = registration['reference_size']
    cw, ch = registration['current_size']
    matrix = np.asarray(registration['current_to_reference'], dtype=float)
    old = np.asarray(fitted['H'], dtype=float)
    if matrix.shape != (3, 3) or old.shape != (3, 3) or not np.isfinite(matrix).all() or min(rw, rh, cw, ch) <= 0:
        raise ValueError('Invalid calibration transfer')
    h = old @ np.diag([1/rw, 1/rh, 1.]) @ matrix @ np.diag([cw, ch, 1.])
    if not np.isfinite(h).all():
        raise ValueError('Invalid calibration transfer')
    return {**fitted, 'H': h, 'camera_registration': {k: v for k, v in registration.items()
                                                   if k not in ('current_to_reference', 'reference_to_current')}}
