"""Fail-closed live calibration transfer with short temporal confirmation.

Registration quality is image-space evidence, never a metre accuracy promise.
No calibration file is modified. An optional review store receives one new,
frozen scene per run, not an expiring stream of replacement questions.
"""
import json
from pathlib import Path
import re

import cv2
import numpy as np

from app.camera_adaptation import CameraAdaptation, transfer_calibration
from app.pitch_map import feet_to_metres


class CameraSession:
    def __init__(self, reference, record, fitted, registrar=None, confirmation_frames=2,
                 stability_fraction=.005, review_store=None):
        self.reference, self.fitted = reference, fitted
        self.registrar = registrar or CameraAdaptation()
        self.confirmation_frames = max(2, confirmation_frames)
        self.stability_fraction = stability_fraction
        self.polygon = None
        if reference is not None and reference.size:
            h, w = reference.shape[:2]
            points = np.asarray([[p['x']*w, p['y']*h] for p in record.get('points', [])], np.float32)
            if len(points) >= 4:
                self.polygon = cv2.convexHull(points).reshape(-1, 2)
        self.previous_projection = None
        self.streak = 0
        self.mapping = None
        self.current_polygon = None
        self.review_store = review_store
        self.review_token = None
        self.review_attempted = False
        self.status = {'state': 'needs_review', 'reason': 'camera_not_checked', 'metric_accuracy_verified': False}

    @classmethod
    def from_record(cls, calibration_path, record, fitted, **kwargs):
        token = record.get('ref_token', '')
        reference = None
        if isinstance(token, str) and re.fullmatch(r'[0-9a-f]{32}', token):
            source = Path(calibration_path).parent.parent / 'pending' / (token + '.jpg')
            reference = cv2.imread(str(source)) if source.is_file() else None
        return cls(reference, record, fitted, **kwargs)

    def _request_review(self, frame, timestamp):
        if self.review_attempted or self.review_store is None:
            return
        self.review_attempted = True
        from app.training_labels import TrainingLabels
        labels = TrainingLabels(self.review_store)
        labels.publish(frame, [], timestamp, 'camera_adaptation', provenance={
            'split': 'unassigned', 'purpose': 'camera_calibration_review',
            'reason': self.status['reason'], 'human_action': '경기장 선의 기준점 4개 이상을 넓게 지정해 주세요.'})
        frozen = labels.freeze()
        self.review_token = frozen['token'] if frozen else None

    def update(self, frame, timestamp=None):
        was_ready = self.mapping is not None
        self.mapping = None
        self.current_polygon = None
        if self.reference is None or self.polygon is None:
            result = {'status': 'needs_review', 'reason': 'calibration_reference_unavailable'}
        else:
            result = self.registrar.fit(self.reference, frame, self.polygon)
        public = {k: v for k, v in result.items() if k not in ('status', 'current_to_reference', 'reference_to_current', 'support_polygon_current')}
        public['metric_accuracy_verified'] = False
        if result.get('status') != 'ready':
            self.previous_projection, self.streak = None, 0
            self.status = {**public, 'state': 'needs_review', 'reset_temporal': was_ready}
            self._request_review(frame, timestamp)
        else:
            try:
                matrix = np.asarray(result['reference_to_current'], float)
                homogeneous = np.column_stack((self.polygon, np.ones(len(self.polygon)))) @ matrix.T
                if not np.isfinite(homogeneous).all() or np.any(np.abs(homogeneous[:, 2]) < 1e-8):
                    raise ValueError('Invalid projected polygon')
                projected = homogeneous[:, :2] / homogeneous[:, 2, None]
                projected /= np.asarray(result['current_size'])
                moved = bool(self.previous_projection is not None and
                             np.max(np.linalg.norm(projected-self.previous_projection, axis=1)) > self.stability_fraction)
                self.streak = 1 if self.previous_projection is None or moved else self.streak+1
                self.previous_projection = projected
                ready = self.streak >= self.confirmation_frames
                if ready:
                    self.mapping = transfer_calibration(self.fitted, result)
                    self.current_polygon = np.asarray(result['support_polygon_current'], np.float32)
                    if (self.current_polygon.ndim != 2 or self.current_polygon.shape[1] != 2
                            or len(self.current_polygon) < 3 or not np.isfinite(self.current_polygon).all()):
                        raise ValueError('Invalid support polygon')
                self.status = {**public, 'state': 'ready' if ready else 'stabilizing',
                               'reason': result['reason'] if ready else 'awaiting_consistent_frames',
                               'consistent_frames': self.streak, 'reset_temporal': was_ready and moved}
            except (ValueError, KeyError, TypeError, np.linalg.LinAlgError):
                self.mapping, self.current_polygon = None, None
                self.previous_projection, self.streak = None, 0
                self.status = {'state': 'needs_review', 'reason': 'invalid_transfer',
                               'reset_temporal': was_ready, 'metric_accuracy_verified': False}
                self._request_review(frame, timestamp)
        self.status.update({'timestamp': timestamp, 'review_token': self.review_token,
                            'review_page': '/train' if self.review_token else None,
                            'reference_rms_m': self.fitted.get('rms'),
                            'pitch': dict(self.fitted.get('pitch', {})),
                            'pitch_dimensions_are_estimates': True})
        return self.status

    def point(self, box, frame):
        if self.mapping is None or self.current_polygon is None:
            return None
        foot = (float((box[0]+box[2])/2), float(box[3]))
        if cv2.pointPolygonTest(self.current_polygon, foot, False) < 0:
            return None
        return feet_to_metres(self.mapping, box, frame.shape[1], frame.shape[0])

    def write_status(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.status, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temporary.replace(path)
