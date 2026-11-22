"""Bounded per-input analysis timeline; input times require an asserted CFR file."""
from collections import deque
import hashlib
import math
from pathlib import Path
import threading

import cv2


def fingerprint(path):
    try:
        p = Path(path).resolve(strict=True)
        stat = p.stat()
        return (str(p), stat.st_size, stat.st_mtime_ns)
    except (ValueError, TypeError, OSError):
        return None


class SequenceHistory:
    def __init__(self, capacity=7200, sample_interval_s=1.0):
        self._lock = threading.Lock()
        self.capacity = capacity
        self.sample_interval_s = sample_interval_s
        self._samples = deque(maxlen=capacity)
        self._source = None
        self._last = None

    def reset(self, source=None):
        with self._lock:
            self._samples.clear()
            self._source = fingerprint(source) if source else None
            self._last = None

    def add(self, source, frame_index, fps, frame, players, metrics, feedback, *, teams_validated, calibration_validated, team_colors=None):
        if frame_index < 0 or not math.isfinite(fps) or not 1 <= fps <= 240:
            return False
        source_id = fingerprint(source)
        if source_id is None:
            return False
        video_time = frame_index / fps
        with self._lock:
            if source_id != self._source or (self._last is not None and video_time < self._last + self.sample_interval_s):
                return False
            # The exact image can be decoded again and verified before saving a
            # clip; no temporary JPEG buffers proportional to duration are held.
            digest = hashlib.sha256(frame.tobytes()).hexdigest()
            safe_players = []
            for p in players:
                safe_players.append({'id': str(p['id']), 'team': p['team'] if teams_validated else 'unknown',
                                     'x': p['x'] if calibration_validated else None,
                                     'y': p['y'] if calibration_validated else None})
            safe_metrics = dict(metrics) if teams_validated and calibration_validated else {'team_width_m': None, 'team_length_m': None}
            safe_feedback = [dict(f) for f in feedback] if teams_validated and calibration_validated else []
            self._samples.append({'frame_index': frame_index, 'fps': fps, 'source_time_s': video_time,
                                  'digest': digest, 'players': safe_players, 'metrics': safe_metrics, 'feedback': safe_feedback,
                                  'team_colors': dict(team_colors) if isinstance(team_colors, dict) else {'home': None, 'away': None}})
            self._last = video_time
            return True

    def find(self, source, start, end):
        with self._lock:
            if fingerprint(source) != self._source or self._source is None:
                return None
            candidates = [x for x in self._samples if start <= x['source_time_s'] < end]
            if not candidates:
                return None
            return dict(min(candidates, key=lambda x: abs(x['source_time_s'] - (start + end) / 2)))


def read_verified_frame(source, snapshot):
    cap = cv2.VideoCapture(str(source))
    try:
        if not cap.isOpened() or not cap.set(cv2.CAP_PROP_POS_FRAMES, snapshot['frame_index']):
            return None
        ok, frame = cap.read()
        if not ok or frame is None or hashlib.sha256(frame.tobytes()).hexdigest() != snapshot['digest']:
            return None
        height, width = frame.shape[:2]
        ratio = min(1., 1920 / width, 1080 / height)
        if ratio < 1:
            frame = cv2.resize(frame, (max(1, round(width*ratio)), max(1, round(height*ratio))), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return encoded.tobytes() if ok and encoded.nbytes <= 2_000_000 else None
    except (cv2.error, OSError, ValueError):
        return None
    finally:
        cap.release()
