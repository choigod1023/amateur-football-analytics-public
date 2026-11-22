"""Conservative changes in the spread of the same observed track IDs.

This does not infer tactical intent, goals, possession or off-screen players.
"""
import math


class FormationObserver:
    def __init__(self, min_interval_s=1., max_interval_s=3., threshold_m=5.):
        self.min_interval_s = min_interval_s
        self.max_interval_s = max_interval_s
        self.threshold_m = threshold_m
        self.reset()

    def reset(self):
        self.anchor = None

    def update(self, players, team, timestamp, field_size_m, *, validated=False):
        if not validated or team not in ('home', 'away'):
            self.reset(); return []
        try:
            t = float(timestamp)
            length, width = map(float, field_size_m)
            if not all(math.isfinite(v) and v > 0 for v in (length, width)) or not math.isfinite(t) or t < 0:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            self.reset(); return []
        positions = {}
        all_ids = set()
        for player in players:
            pid = player.get('id')
            if not isinstance(pid, str) or not pid or pid in all_ids:
                self.reset(); return []
            all_ids.add(pid)
            if player.get('team') != team:
                continue
            try:
                x, y = float(player['x']), float(player['y'])
                if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
                    raise ValueError
            except (ValueError, TypeError, KeyError, OverflowError):
                self.reset(); return []
            positions[pid] = (x, y)
        if len(positions) < 3:
            self.reset(); return []
        old = self.anchor
        if old is None or old[2] != (length, width) or t <= old[0] or t-old[0] > self.max_interval_s:
            self.anchor = (t, positions, (length, width)); return []
        # Keep only IDs present throughout the entire interval. New arrivals do
        # not invalidate the existing group, and departures cannot distort its
        # previously measured extent. Missing IDs cannot re-enter this anchor.
        shared = {pid: point for pid, point in old[1].items() if pid in positions}
        if len(shared) < 3:
            self.anchor = (t, positions, (length, width)); return []
        self.anchor = (old[0], shared, old[2])
        if t-old[0] < self.min_interval_s:
            return []
        self.anchor = (t, positions, (length, width))
        before = [shared[pid] for pid in shared]
        after = [positions[pid] for pid in shared]
        def extent(points, axis, scale):
            values = [p[axis] for p in points]
            return (max(values) - min(values)) * scale
        changes = []
        for key, axis, scale in (('team_length_m', 0, length), ('team_width_m', 1, width)):
            previous, now = extent(before, axis, scale), extent(after, axis, scale)
            delta = now - previous
            if abs(delta) >= self.threshold_m:
                changes.append({'metric': key, 'previous_m': round(previous, 2), 'current_m': round(now, 2),
                                'change_m': round(delta, 2), 'interval_s': round(t-old[0], 3),
                                'observed_players': len(shared)})
        return changes


def observation_feedback(change):
    axis = '폭' if change['metric'] == 'team_width_m' else '길이'
    direction = '늘었습니다' if change['change_m'] > 0 else '줄었습니다'
    return {'observation': f"같은 추적 ID {change['observed_players']}명의 화면 내 {axis}이 {change['interval_s']}초 동안 {abs(change['change_m'])}m {direction}.",
            'interpretation': '화면에 보인 선수들의 간격 변화이며 전술 의도나 성공 여부는 알 수 없습니다.',
            'suggestion': '원본 영상에서 공과 상대 선수의 위치, 화면 밖 상황을 함께 확인해 주세요.',
            'limitations': '화면 밖 선수, 카메라 움직임, 보정·팀 분류 오류, 가림과 추적 ID 변경이 결과에 영향을 줄 수 있습니다.'}
