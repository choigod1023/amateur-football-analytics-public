"""Collect the frames where the person detector probably missed players, during a live run, for the user to draw boxes on later.

Rules are cheap (a few counts per analysed frame; the image is only encoded when a frame is saved). Saved frames go to a folder of their own, never into the
human label store: every row carries origin 'hard_frame_collector' and status 'unreviewed'. Measured rules and limits: wiki/hard-frames.md.
"""
import json
import os
import threading
from collections import deque
from pathlib import Path

ORIGIN = 'hard_frame_collector'
NEON_MIN, DARK_MIN = 0.10, 0.30          # the shirt colour rule of scripts/run_live_feedback.py (neon = team A, dark = team B)

DEFAULTS = {
    'history_seconds': 4.0,    # the recent past the drop rules compare with
    'min_history': 8,          # analysed frames needed before the drop rules may fire
    'drop': 4,                 # persons fewer than the median of the history
    'low_total': 0,            # fewer persons than this in one frame (0 = rule off)
    'team_low': 0,             # fewer persons of the focus team than this (0 = rule off)
    'team_drop': 0,            # focus team persons fewer than the median of the history by this many (0 = rule off)
    'disagree': 0,             # persons of a second detector (score >= other_score) that this detector lacks (0 = rule off; needs other_boxes)
    'other_score': 0.35,
    'min_gap': 20.0,           # seconds between two saved frames
    'max_frames': 60,          # saved frames in one run
}


def colour_counts(frame, detections):
    """{'n': persons, 'neon': neon shirts, 'dark': dark shirts} of one frame (detections: [x1, y1, x2, y2, score])."""
    from app.team_role_features import FEATURE_NAMES, box_features
    h, w = frame.shape[:2]
    neon, dark = FEATURE_NAMES.index('neon'), FEATURE_NAMES.index('dark')
    a = b = 0
    for d in detections:
        f = box_features(frame, [d[0] / w, d[1] / h, d[2] / w, d[3] / h])
        if f[neon] >= NEON_MIN:
            a += 1
        elif f[dark] >= DARK_MIN:
            b += 1
    return {'n': len(detections), 'neon': a, 'dark': b}


def _median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _iou(a, b):
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    i = w * h
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def judge(history, n_total, n_team, boxes=None, other_boxes=None, settings=None):
    """The reasons a frame is suspicious (empty list: not). history: [(n_total, n_team), ...] of the frames just before."""
    s = {**DEFAULTS, **(settings or {})}
    reasons = []
    enough = len(history) >= s['min_history']
    if enough and s['drop'] and _median([h[0] for h in history]) - n_total >= s['drop']:
        reasons.append('count_drop')
    if s['low_total'] and n_total < s['low_total']:
        reasons.append('low_total')
    if s['team_low'] and n_team is not None and n_team < s['team_low']:
        reasons.append('team_low')
    if enough and s['team_drop'] and n_team is not None:
        past = [h[1] for h in history if h[1] is not None]
        if past and _median(past) - n_team >= s['team_drop']:
            reasons.append('team_drop')
    if s['disagree'] and other_boxes is not None and boxes is not None:
        lacking = [o for o in other_boxes if o[4] >= s['other_score'] and all(_iou(o, b) < 0.3 for b in boxes)]
        if len(lacking) >= s['disagree']:
            reasons.append('detectors_disagree')
    return reasons


class HardFrameCollector:
    """observe() once per analysed frame; saves the frame when a rule fires and the budget (min_gap, max_frames) allows it."""

    def __init__(self, folder, camera='', detector='', settings=None):
        self.folder = Path(folder)
        self.settings = {**DEFAULTS, **(settings or {})}
        self.camera, self.detector = camera, detector
        self.history = deque()                                                            # (second, persons, focus team persons)
        self.saved = 0
        self.last_saved = None
        self.flagged = 0                                                                  # frames a rule fired on, saved or not (for the summary)
        self.lock = threading.Lock()
        (self.folder / 'frames').mkdir(parents=True, exist_ok=True)
        self.index_path = self.folder / 'hard_frames.jsonl'
        if self.index_path.exists():                                                      # a run that is continued keeps counting
            with open(self.index_path, encoding='utf-8') as f:
                self.saved = sum(1 for line in f if line.strip())

    def observe(self, t, frame, boxes, n_team=None, camera=None, other_boxes=None):
        """boxes: [[x1, y1, x2, y2, score], ...] of this frame. Returns the saved row, or None."""
        s = self.settings
        n_total = len(boxes)
        reasons = judge([(h[1], h[2]) for h in self.history], n_total, n_team, boxes, other_boxes, s)
        self.history.append((t, n_total, n_team))
        while self.history and t - self.history[0][0] > s['history_seconds']:
            self.history.popleft()
        if not reasons:
            return None
        self.flagged += 1
        if self.saved >= s['max_frames'] or (self.last_saved is not None and 0 <= t - self.last_saved < s['min_gap']):
            return None
        return self._save(t, frame, boxes, reasons, n_team, camera or self.camera)

    def _save(self, t, frame, boxes, reasons, n_team, camera):
        import cv2
        name = f'hf_{int(round(t * 10)):07d}'
        path = self.folder / 'frames' / (name + '.jpg')
        if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90]):
            return None
        h, w = frame.shape[:2]
        row = {'origin': ORIGIN, 'status': 'unreviewed', 'id': name, 'image': 'frames/' + name + '.jpg', 'video_time': round(float(t), 2), 'camera': camera,
               'reasons': reasons, 'detector': self.detector, 'width': w, 'height': h, 'n_boxes': len(boxes), 'n_team': n_team,
               'boxes': [[round(float(v), 1) for v in b[:4]] + [round(float(b[4]), 3)] for b in boxes]}
        with self.lock:
            with open(self.index_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
        self.saved += 1
        self.last_saved = t
        return row

    def summary(self):
        return {'saved': self.saved, 'flagged': self.flagged, 'folder': str(self.folder)}
