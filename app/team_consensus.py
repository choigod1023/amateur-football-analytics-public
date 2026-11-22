"""Short-lived, conservative per-track observations; no model learning."""
import math
from collections import Counter


class TeamConsensus:
    def __init__(self, required=3, max_gap_s=1.0):
        if not isinstance(required, int) or isinstance(required, bool) or required < 2 or not math.isfinite(max_gap_s) or max_gap_s <= 0:
            raise ValueError('Invalid consensus settings')
        self.required = required
        self.max_gap_s = max_gap_s
        self.tracks = {}
        self.last_time = None

    def reset(self):
        self.tracks.clear()
        self.last_time = None

    def update(self, players, timestamp):
        timestamp = float(timestamp)
        if not math.isfinite(timestamp) or (self.last_time is not None and timestamp <= self.last_time):
            self.reset()
            return [dict(p, team='unknown') for p in players]
        self.last_time = timestamp
        ids = Counter(p.get('id') for p in players if isinstance(p.get('id'), str) and p.get('id'))
        self.tracks = {pid: state for pid, state in self.tracks.items()
                       if ids[pid] == 1 and timestamp - state[2] <= self.max_gap_s}
        result = []
        for player in players:
            pid, team = player.get('id'), player.get('team')
            if not isinstance(pid, str) or not pid or ids[pid] != 1 or team not in ('home', 'away'):
                if isinstance(pid, str):
                    self.tracks.pop(pid, None)
                result.append(dict(player, team='unknown'))
                continue
            previous = self.tracks.get(pid)
            count = previous[1] + 1 if previous and previous[0] == team else 1
            self.tracks[pid] = (team, min(count, self.required), timestamp)
            result.append(dict(player, team=team if count >= self.required else 'unknown'))
        return result
