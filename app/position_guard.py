"""Reject implausible displacement from recent accepted observations.

Rejected measurements never become an anchor. Missing people are not emitted;
only a bounded history is retained to check their next observed position.
"""
import math


class PositionGuard:
    def __init__(self, max_speed=12., max_gap=.6):
        if not all(math.isfinite(v) and v > 0 for v in (max_speed, max_gap)):
            raise ValueError('Positive finite speed and gap limits required')
        self.previous = {}
        self.last_time = None
        self.max_speed, self.max_gap = max_speed, max_gap

    def filter(self, t, teams):
        if not math.isfinite(t) or t == self.last_time:
            return {team: [] for team in teams}, sum(len(rows) for rows in teams.values())
        if self.last_time is not None and t < self.last_time:
            self.previous.clear()  # Explicit time-domain restart, not a trajectory.
        self.last_time = t
        current = {key: value for key, value in self.previous.items()
                   if 0 < t-value[0] <= self.max_gap + 1e-9}
        output, rejected, seen = {}, 0, set()
        for team, rows in teams.items():
            kept = []
            for tid, x, y in rows:
                key = (team, tid)
                if key in seen or not all(math.isfinite(v) for v in (x, y)):
                    rejected += 1
                    continue
                seen.add(key)
                prior = current.get(key)
                if prior:
                    if math.hypot(x-prior[1], y-prior[2])/(t-prior[0]) > self.max_speed:
                        rejected += 1
                        continue
                current[key] = (t, x, y)
                kept.append((tid, x, y))
            output[team] = kept
        self.previous = current
        return output, rejected


class DisplayPositionGuard:
    """Filter-to-raw transitions must not introduce a new display teleport."""
    def __init__(self, max_speed=12., max_gap=.6):
        if not all(math.isfinite(v) and v > 0 for v in (max_speed, max_gap)):
            raise ValueError('Positive finite speed and gap limits required')
        self.previous={}
        self.last_time=None
        self.max_speed,self.max_gap=max_speed,max_gap

    def filter(self,t,raw,proposed):
        if not math.isfinite(t) or t == self.last_time:
            return {team: [] for team in proposed}, {'raw_fallbacks': 0, 'omitted': sum(len(rows) for rows in proposed.values())}
        if self.last_time is not None and t < self.last_time:
            self.previous.clear()
        self.last_time=t
        current={key:value for key,value in self.previous.items() if 0<t-value[0]<=self.max_gap+1e-9}
        result={};fallbacks=dropped=0;seen=set()
        lookup={(team,tid):(x,y) for team,rows in raw.items() for tid,x,y in rows}
        for team,rows in proposed.items():
            kept=[]
            for tid,x,y in rows:
                key=(team,tid)
                if key not in lookup:continue
                if key in seen or not all(math.isfinite(v) for v in (x,y,*lookup[key])):
                    dropped+=1
                    continue
                seen.add(key)
                old=current.get(key)
                if old:
                    limit=self.max_speed*(t-old[0])
                    if math.hypot(x-old[1],y-old[2])>limit:
                        x,y=lookup[key];fallbacks+=1
                        if math.hypot(x-old[1],y-old[2])>limit:
                            dropped+=1
                            continue
                kept.append((tid,x,y));current[key]=(t,x,y)
            result[team]=kept
        self.previous=current
        return result,{'raw_fallbacks':fallbacks,'omitted':dropped}
