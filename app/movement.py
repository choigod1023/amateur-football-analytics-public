"""Conservative movement observations using verified *video* timestamps.

The caller must reset this object on a new stream or calibration, and provide
timestamps from a reliable media timeline, not analysis wall-clock time.
"""
import math


class MovementTracker:
    def __init__(self, min_interval_s=0.25, max_interval_s=2.0, max_speed_m_s=10.0, min_distance_m=0.2):
        self.min_interval_s = min_interval_s
        self.max_interval_s = max_interval_s
        self.max_speed_m_s = max_speed_m_s
        self.min_distance_m = min_distance_m
        self.reset()

    def reset(self):
        self.anchors = {}
        self.last_time = None
        self.field_size = None

    def update(self, players, video_time_s, field_size_m, *, calibration_validated=False, teams_validated=False, timeline_reliable=False):
        """Return observed movement records and limited coaching, never guesses.

        x/y must be normalized length/width coordinates. An ID must be present
        and on the same team in every update between its two sampled positions.
        A plausible speed cannot prove identity continuity or calibration.
        """
        if not (calibration_validated and teams_validated and timeline_reliable):
            self.reset()
            return [], []
        try:
            timestamp = float(video_time_s)
            dims = tuple(float(v) for v in field_size_m)
            if not math.isfinite(timestamp) or timestamp < 0 or len(dims) != 2 or any(not math.isfinite(v) or v <= 0 for v in dims):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            self.reset()
            return [], []
        if self.field_size != dims or (self.last_time is not None and (timestamp <= self.last_time or timestamp - self.last_time > self.max_interval_s)):
            self.reset()
        self.field_size = dims
        self.last_time = timestamp

        # Duplicate IDs are ambiguous, so discard every occurrence of that ID.
        occurrences = {}
        for player in players:
            pid = player.get('id')
            if isinstance(pid, str) and pid:
                occurrences[pid] = occurrences.get(pid, 0) + 1
        valid = {}
        for p in players:
            pid, team = p.get('id'), p.get('team')
            if not isinstance(pid, str) or not pid or occurrences.get(pid) != 1 or team not in ('home', 'away'):
                continue
            try:
                x, y = float(p['x']), float(p['y'])
                if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 1 and 0 <= y <= 1):
                    continue
            except (TypeError, KeyError, ValueError, OverflowError):
                continue
            valid[pid] = (team, x, y)
        self.anchors = {pid: anchor for pid, anchor in self.anchors.items() if pid in valid and anchor[1] == valid[pid][0]}
        observations = []
        for pid, (team, x, y) in valid.items():
            old = self.anchors.get(pid)
            if old is None:
                self.anchors[pid] = (timestamp, team, x, y)
                continue
            elapsed = timestamp - old[0]
            if elapsed < self.min_interval_s:
                continue
            self.anchors[pid] = (timestamp, team, x, y)
            if elapsed > self.max_interval_s:
                continue
            distance = math.hypot((x-old[2])*dims[0], (y-old[3])*dims[1])
            speed = distance / elapsed
            if distance < self.min_distance_m or speed > self.max_speed_m_s:
                continue
            observations.append({'id': pid, 'team': team, 'displacement_m': round(distance, 2), 'interval_s': round(elapsed, 3), 'average_speed_m_s': round(speed, 2)})
        feedback = []
        if observations:
            feedback.append({
                'observation': f"연속 관측된 {len(observations)}명의 위치 변화를 확인했습니다.",
                'interpretation': '두 관측 지점 사이의 직선 변위이며 실제 이동 경로나 전술 의도를 뜻하지 않습니다.',
                'suggestion': '원본 영상에서 해당 선수의 움직임과 주변 상황을 함께 확인해 주세요.',
                'limitations': '화면 밖 선수, 가림과 추적 ID 전환, 팀 분류 및 보정 오차가 결과에 영향을 줄 수 있습니다. 실제 속도 검증은 하지 않았습니다.',
            })
        return observations, feedback
