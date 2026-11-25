"""Goalkeeper mark from where a person stays: a track that spent most of the last seconds in front of a goal gets the role 'keeper_zone'.

Why: the goalkeeper stands in the goal area and wears no bib, so the shirt-colour vote gives him no team letter and he never reaches the record.
Staying in front of a goal is a different evidence from colour: a field player passes through the goal area, he does not live there.
This rule only adds a mark. It never removes a point and never changes a team letter; unlettered tracks are marked too, because they are the point.

Rule (past frames only, plain arithmetic on the tracks of one frame):
* zone: the goal area of Law 1 (5.5 m deep, 18.32 m wide, so |y| <= 9.16 m) in front of either goal line, plus GOAL_LINE_SLACK_M behind the line
  (foot noise of a box at this camera);
* a track is marked when in the last WINDOW_S seconds it was seen at least MIN_SEEN_S seconds and at least SHARE_MIN of its sightings lie in the
  zone of one goal;
* at most one track per goal and frame is marked (a team has one goalkeeper on the pitch): the one with the largest share, then the longest sighting;
  the other qualifying tracks of that goal are counted in `crowded` and not marked.
Values: the zone from the Laws of the Game, WINDOW_S and MIN_SEEN_S, SHARE_MIN fixed on the first 10 minutes of the 11-20 first half only (see
work/model-improve-1123/keeper-zone/results.md).

Geometry: pitch metres as the live script places them, x toward the right of the picture. direction = +1 when the focus team attacks +x, so its own
goal is at x = -length / 2; 'left'/'right' name the goal by the sign of x, 'own'/'opp' by the focus team.
"""
from collections import deque

GOAL_AREA_DEPTH_M = 5.5        # Law 1
GOAL_AREA_HALF_WIDTH_M = 9.16  # Law 1: goal area 18.32 m wide
GOAL_LINE_SLACK_M = 1.0        # a foot point up to this far behind the goal line still counts as in front of the goal
WINDOW_S = 10.0                # the past this long is looked at
MIN_SEEN_S = 5.0               # a track has to have been seen this long inside the window before it can be marked
SHARE_MIN = 0.8                # share of its sightings in the window that lie in the zone


def zone_goal(x, y, length=89.0, half_width=GOAL_AREA_HALF_WIDTH_M, depth=GOAL_AREA_DEPTH_M, slack=GOAL_LINE_SLACK_M):
    """+1 when (x, y) lies in front of the goal at x = +length / 2, -1 for the goal at x = -length / 2, else 0."""
    if abs(y) > half_width:
        return 0
    ax = abs(x)
    if length / 2 - depth <= ax <= length / 2 + slack:
        return 1 if x > 0 else -1
    return 0


class KeeperZone:
    """kz = KeeperZone(length)
    marks = kz.update(t, direction, people)
      people: [(track id, x, y) or (track id, x, y, team letter or None)] of every tracked person on the pitch, lettered or not
      returns [{'id', 'x', 'y', 'goal': 'left'|'right', 'side': 'own'|'opp', 'letter'}] (at most one per goal)
    self.crowded = number of further qualifying tracks left unmarked in the last frame."""

    def __init__(self, pitch_length=89.0, window=WINDOW_S, min_seen=MIN_SEEN_S, share_min=SHARE_MIN):
        self.length, self.window, self.min_seen, self.share_min = float(pitch_length), float(window), float(min_seen), float(share_min)
        self.history = {}      # track id -> deque of (t, goal -1/0/+1)
        self.in_zone = {}      # track id -> {-1: n, +1: n} sightings in the window
        self.seen = {}         # track id -> sightings in the window
        self.crowded = 0
        self.candidates = 0    # qualifying tracks of the last frame before the one-per-goal choice

    def _push(self, tid, t, goal):
        h = self.history.setdefault(tid, deque())
        h.append((t, goal))
        self.seen[tid] = self.seen.get(tid, 0) + 1
        if goal:
            c = self.in_zone.setdefault(tid, {-1: 0, 1: 0})
            c[goal] += 1

    def _trim(self, tid, t):
        h = self.history[tid]
        while h and h[0][0] < t - self.window:
            _, goal = h.popleft()
            self.seen[tid] -= 1
            if goal:
                self.in_zone[tid][goal] -= 1

    def update(self, t, direction, people):
        present = set()
        positions = {}
        for p in people:
            tid, x, y = int(p[0]), p[1], p[2]
            present.add(tid)
            positions[tid] = (x, y, p[3] if len(p) > 3 else None)
            self._push(tid, t, zone_goal(x, y, self.length))
        for tid in list(self.history):
            self._trim(tid, t)
            if not self.history[tid]:
                del self.history[tid], self.seen[tid]
                self.in_zone.pop(tid, None)
        best = {}                                    # goal -> (share, span, tid)
        qualifying = 0
        for tid in present:
            h = self.history[tid]
            span = h[-1][0] - h[0][0]
            c = self.in_zone.get(tid)
            if not c or span < self.min_seen:
                continue
            for goal in (-1, 1):
                if c[goal] and c[goal] / self.seen[tid] >= self.share_min and zone_goal(positions[tid][0], positions[tid][1], self.length) == goal:
                    qualifying += 1
                    key = (c[goal] / self.seen[tid], span, -tid)
                    if goal not in best or key > best[goal][0]:
                        best[goal] = (key, tid)
        self.candidates = qualifying
        self.crowded = qualifying - len(best)
        marks = []
        for goal, (_, tid) in sorted(best.items()):
            x, y, letter = positions[tid]
            own = -1 if direction > 0 else 1         # the goal of the focus team: x = -length / 2 when it attacks +x
            marks.append({'id': tid, 'x': round(float(x), 2), 'y': round(float(y), 2), 'goal': 'right' if goal > 0 else 'left', 'side': 'own' if goal == own else 'opp', 'letter': letter})
        return marks


class SafeKeeperZone:
    """Wraps KeeperZone for the live loop: if the mark calculation raises, one warning is printed (once per run) and that frame gets an empty
    mark list; the alerts and the record of the frame are not skipped.
    marks = SafeKeeperZone(kz).update(t, direction, build_people)   # build_people() -> people list, it may raise too"""

    def __init__(self, kz, warn=None):
        self.kz = kz
        self.warn = warn or (lambda message: print(message, flush=True))
        self.warned = False
        self.failed_frames = 0

    def update(self, t, direction, build_people):
        try:
            return self.kz.update(t, direction, build_people())
        except Exception as error:  # the mark is an extra; it must never stop the frame
            self.failed_frames += 1
            if not self.warned:
                self.warned = True
                self.warn(f'Warning: the keeper zone mark failed ({type(error).__name__}: {error}); frames with a failed mark get an empty keeper_zone, the run goes on.')
            return []
