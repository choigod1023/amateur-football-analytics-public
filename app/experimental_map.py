"""Unverified short-lived map candidates; never input to tactical metrics."""
from collections import Counter
import math
import cv2
import numpy as np


class ExperimentalMap:
    def __init__(self, max_age=0.8, max_speed_m_s=12.0, max_players=22):
        self.max_age = max_age
        self.max_speed = max_speed_m_s
        self.max_players = max_players
        self.history = {}
        self.capacity = {'observed': 0, 'estimated_suppressed': 0, 'observed_over_limit': 0}

    def clear(self):
        self.history.clear()
        self.capacity = {'observed': 0, 'estimated_suppressed': 0, 'observed_over_limit': 0}

    def forget(self, ids):
        for tid in ids:
            self.history.pop(str(tid), None)

    def update(self, points, now, field_size, *, allow_estimation=True, allowed_polygon=None):
        """Observed inputs (id,x,y,team_hint) are normalized field coordinates.

        Only extend previously observed IDs using their last two observations.
        Error bounds are not calibrated, so uncertainty_m remains null.
        """
        if not math.isfinite(now) or len(field_size) != 2:
            self.clear()
            return []
        counts = Counter(str(p['id']) for p in points)
        visible = set()
        result = []
        for p in points:
            tid = str(p['id'])
            x, y = p['x'], p['y']
            if counts[tid] != 1 or not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
                self.history.pop(tid, None)
                continue
            visible.add(tid)
            previous = self.history.get(tid)
            hint = p.get('team_hint') if p.get('team_hint') in (0, 1) else None
            current = (float(x), float(y), float(now), hint)
            history = (previous['last'], current) if previous and 0 < now-previous['last'][2] <= 0.6 else None
            self.history[tid] = {'last': current, 'pair': history}
            result.append({'id': tid, 'x': x, 'y': y, 'team_hint': hint, 'kind': 'observed', 'age_s': 0.0, 'uncertainty_m': None})
        observed_count = len(result)
        estimated = []
        for tid, item in list(self.history.items()):
            if tid in visible:
                continue
            x, y, timestamp, hint = item['last']
            age = now-timestamp
            if age <= 0 or age > self.max_age:
                self.history.pop(tid, None)
                continue
            if not allow_estimation:
                continue
            pair = item['pair']
            if not pair:
                continue
            first, last = pair
            dt = last[2]-first[2]
            if dt < 0.05:
                continue
            vx, vy = (last[0]-first[0])/dt, (last[1]-first[1])/dt
            speed = math.hypot(vx*field_size[0], vy*field_size[1])
            if not math.isfinite(speed) or speed > self.max_speed:
                continue
            px, py = x+vx*age, y+vy*age
            if not (0 <= px <= 1 and 0 <= py <= 1):
                continue
            if allowed_polygon is not None:
                polygon = np.asarray(allowed_polygon, dtype=np.float32)
                if polygon.shape != (4, 2) or not np.isfinite(polygon).all() or cv2.pointPolygonTest(polygon, (float(px*field_size[0]), float(py*field_size[1])), True) < -.01:
                    continue
            estimated.append({'id': tid, 'x': px, 'y': py, 'team_hint': hint, 'kind': 'estimated', 'age_s': round(age, 2), 'uncertainty_m': None})
        # A football roster limits how many unobserved guesses we show, not
        # how many actual detections exist. Referees and false positives can
        # make observed candidates exceed 22; never silently hide them.
        estimated.sort(key=lambda p: (p['age_s'], p['id']))
        available = max(0, self.max_players - observed_count)
        self.capacity = {'observed': observed_count,
                         'estimated_suppressed': max(0, len(estimated) - available),
                         'observed_over_limit': max(0, observed_count - self.max_players)}
        result.extend(estimated[:available])
        return result
