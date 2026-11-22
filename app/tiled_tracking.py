"""Experimental horizontal image tiling followed by one whole-frame tracker.

Coordinate conversion and NMS operate on the original image, so tile boundaries
do not create independent tracking timelines. This does not handle camera motion.
"""
import math
import numpy as np


def use_tiled_detection(setting, width, height):
    """Choose once per input; only very wide frames use the automatic mode."""
    if setting == 'auto':
        return width > 0 and height > 0 and width / height >= 3.0
    return setting is True


def tile_windows(width, height, overlap=0.2, max_tiles=12):
    if width <= 0 or height <= 0 or not (0 <= overlap < 1) or max_tiles < 2:
        raise ValueError('Invalid frame dimensions or tiling parameters')
    # Cap inference work for unusually wide panoramas without leaving gaps.
    tile_width = min(width, max(height, math.ceil(width / (1 + (max_tiles - 1) * (1 - overlap)))))
    if tile_width == width:
        return [(0, width)]
    stride = max(1, int(tile_width * (1 - overlap)))
    starts = list(range(0, width - tile_width + 1, stride))
    if starts[-1] != width - tile_width:
        starts.append(width - tile_width)
    if len(starts) > max_tiles:
        starts = [round(i * (width - tile_width) / (max_tiles - 1)) for i in range(max_tiles)]
    return [(start, start + tile_width) for start in starts]


def merge_boxes(boxes, width, height, iou_threshold=0.5):
    """Filter invalid xyxy/conf detections, then suppress cross-tile duplicates."""
    valid = []
    for x1, y1, x2, y2, score in boxes:
        if not np.isfinite([x1, y1, x2, y2, score]).all() or not 0 <= score <= 1:
            continue
        x1, x2 = max(0., float(x1)), min(float(width), float(x2))
        y1, y2 = max(0., float(y1)), min(float(height), float(y2))
        if x2 > x1 and y2 > y1:
            valid.append([x1, y1, x2, y2, float(score), 0.])
    valid.sort(key=lambda box: -box[4])
    # Bound quadratic NMS in crowded or adversarial imagery. This can omit
    # people in unusually crowded scenes and does not imply full coverage.
    valid = valid[:300]
    kept = []
    for b in valid:
        def iou(a):
            intersection = max(0., min(a[2], b[2])-max(a[0], b[0])) * max(0., min(a[3], b[3])-max(a[1], b[1]))
            union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
            return intersection / union if union > 0 else 0.
        if all(iou(a) <= iou_threshold for a in kept):
            kept.append(b)
    return np.asarray(kept, dtype=np.float32).reshape(-1, 6)


class TiledPlayerTracker:
    def __init__(self, model, device, imgsz, confidence, low_score_recovery=False):
        # Keep a distinct predictor from model.track and ball inference; process
        # one tracker update per full frame, even when no people were detected.
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.utils import IterableSimpleNamespace, YAML
        from ultralytics.utils.checks import check_yaml
        cfg = IterableSimpleNamespace(**YAML.load(check_yaml('bytetrack.yaml')))
        if low_score_recovery:
            # Keep births/high-confidence association at the configured gate.
            # Low-score boxes can only be used by ByteTrack's second association.
            cfg.track_high_thresh = confidence
            cfg.new_track_thresh = confidence
        self.tracker = BYTETracker(args=cfg)
        self.model, self.device, self.imgsz, self.confidence = model, device, imgsz, confidence
        self.detector_confidence = min(confidence, cfg.track_low_thresh) if low_score_recovery else confidence

    def reset(self):
        """Clear track association history at an explicit source discontinuity."""
        self.tracker.reset()

    def update(self, frame):
        from ultralytics.engine.results import Boxes
        height, width = frame.shape[:2]
        detections = []
        for left, right in tile_windows(width, height):
            result = self.model.predict(frame[:, left:right], device=self.device, imgsz=self.imgsz,
                                        conf=self.detector_confidence, classes=[0], max_det=100, verbose=False)[0]
            if result.boxes is None:
                continue
            for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                x1, y1, x2, y2 = map(float, box)
                detections.append([x1 + left, y1, x2 + left, y2, float(score)])
        merged = merge_boxes(detections, width, height)
        tracked = self.tracker.update(Boxes(merged, (height, width)), frame)
        return [(row[:4], int(row[4])) for row in tracked]
