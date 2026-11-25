"""Optional linking rules for the live person tracker (ultralytics BYTETracker), all off by default.

Why: at 5 analysed frames per second a jogging player moves about one box width per frame. When a player is missed for a frame or two,
the tracker's coasted box (constant velocity) drifts away and the player comes back under a new number (2026-11-22 study,
work/model-improve-1122/track-breaks: 93 % of the wrong new numbers had no overlap with the coasted box, while the player was a median
1.35 m from his last position). The rules below use the pitch position of the feet, which the live run computes anyway. They use only
past frames and add well under a millisecond per frame (measured in work/model-improve-1122/track-link).

  pitch_link       after the normal overlap stage, a lost number and a left-over detection are joined when the feet are close on the pitch:
                   distance between the number's last foot point and the detection's foot point <= r0 + vmax * seconds lost (and the number has
                   been lost for at most max_age_s seconds when that is set).
  revive           a detection about to start a new number takes a lost number inside the same gate instead, only when the two are each other's
                   nearest and the next candidate on either side is at least `margin` metres farther; otherwise a new number (a break is better
                   than a wrong link). Together with pitch_link the same rule replaces the plain assignment of pitch_link.
  team_gate        a lost number whose team vote is known never joins a detection whose own shirt colour says the other team (unknown colours do
                   not block).
  decay_half_life  the predicted velocity of a lost number fades with this half-life (seconds), so its coasted box stops drifting.
A pitch link starts the motion model of the number afresh on the new box.

The measured effect and the photo check of the joined numbers are in work/model-improve-1122/track-link (tables.md, photos/).
"""
import math

import numpy as np
from ultralytics.trackers.basetrack import TrackState
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.trackers.utils import matching

# Gate values: r0 1.5 m and margin 0.5 m were fixed in advance. The advance values vmax 7 m/s without an age limit joined too much
# (photo check of 50 random joins: 20 wrong, 19 right); vmax 3 m/s with at most 2 s lost was chosen AFTER that on the first-half
# segment and checked on the second half and on 50 photos (3 wrong, 36 right, 11 unclear; model judgement). See track-link/RESULTS.md.
DEFAULT_LINK = {'pitch_link': False, 'decay_half_life': None, 'revive': False, 'team_gate': False,
                'r0': 1.5, 'vmax': 3.0, 'margin': 0.5, 'max_age_s': 2.0}


def link_enabled(link):
    """True when any rule is switched on."""
    link = link or {}
    return bool(link.get('pitch_link') or link.get('revive') or link.get('team_gate') or link.get('decay_half_life'))


def mutual_nearest(cost, margin):
    """Pairs (row, column) of a cost matrix (inf = not allowed) that are each other's nearest, with the second best of the row and of the
    column at least `margin` farther."""
    pairs = []
    if cost.size == 0:
        return pairs
    for i in range(cost.shape[0]):
        row = cost[i]
        j = int(np.argmin(row))
        if not np.isfinite(row[j]):
            continue
        col = cost[:, j]
        if int(np.argmin(col)) != i:
            continue
        r2 = np.partition(row, 1)[1] if row.size > 1 else np.inf
        c2 = np.partition(col, 1)[1] if col.size > 1 else np.inf
        if r2 - row[j] < margin or c2 - col[i] < margin:
            continue
        pairs.append((i, j))
    return pairs


def assign(cost):
    """Minimum-cost assignment of a cost matrix with inf for forbidden pairs."""
    if cost.size == 0:
        return []
    big = 1e6
    matches, _, _ = matching.linear_assignment(np.where(np.isfinite(cost), cost, big), thresh=big - 1)
    return [(int(i), int(j)) for i, j in matches if np.isfinite(cost[i, j])]


class LinkTracker(BYTETracker):
    """BYTETracker with the optional rules above. update(results, img, feet=None, det_teams=None, track_team=None):
    feet: (N, 2) pitch metres of the foot point of every detection (nan when unknown); det_teams: team letter or None per detection;
    track_team: function track id -> team letter or None (the running vote). Without feet the pitch rules do nothing."""

    def __init__(self, args, link=None, fps=5.0):
        super().__init__(args)
        unknown = set(link or {}) - set(DEFAULT_LINK)
        if unknown:
            raise ValueError(f'unknown link options: {sorted(unknown)}')
        self.link = {**DEFAULT_LINK, **(link or {})}
        if self.link['r0'] < 0 or self.link['vmax'] < 0 or self.link['margin'] < 0:
            raise ValueError('r0, vmax and margin must not be negative')
        if self.link['decay_half_life'] is not None and self.link['decay_half_life'] < 0:
            raise ValueError('decay_half_life must not be negative')
        if fps <= 0:
            raise ValueError('fps must be positive')
        self.fps = fps
        self.events = []
        self._feet = self._teams = self._track_team = None

    def _foot(self, det):
        if self._feet is None:
            return None
        f = self._feet[int(det.idx)]
        return f if np.isfinite(f).all() else None

    def _conflict(self, track, det):
        if not self.link['team_gate'] or self._teams is None or self._track_team is None:
            return False
        a, b = self._track_team(track.track_id), self._teams[int(det.idx)]
        return a is not None and b is not None and a != b

    def _cost(self, tracks, dets):
        cost = np.full((len(tracks), len(dets)), np.inf)
        for i, t in enumerate(tracks):
            last = getattr(t, 'last_foot', None)
            if last is None:
                continue
            lost_s = (self.frame_id - t.end_frame) / self.fps
            if self.link['max_age_s'] is not None and lost_s > self.link['max_age_s']:
                continue
            gate = self.link['r0'] + self.link['vmax'] * lost_s
            for j, d in enumerate(dets):
                f = self._foot(d)
                if f is None or self._conflict(t, d):
                    continue
                dist = math.hypot(f[0] - last[0], f[1] - last[1])
                if dist <= gate:
                    cost[i, j] = dist
        return cost

    def _link(self, track, det, kind, dist, refind):
        self.events.append({'kind': kind, 'frame': self.frame_id, 'track_id': int(track.track_id), 'det_idx': int(det.idx),
                            'gap_frames': int(self.frame_id - track.end_frame), 'dist': round(float(dist), 3)})
        track.mean, track.covariance = self.kalman_filter.initiate(track.convert_coords(det._tlwh))
        track.tracklet_len = 0
        track.state = TrackState.Tracked
        track.is_activated = True
        track.frame_id = self.frame_id
        track.score, track.cls, track.idx = det.score, det.cls, det.idx
        refind.append(track)

    def update(self, results, img=None, feats=None, feet=None, det_teams=None, track_team=None, **kwargs):
        self._feet = None if feet is None else np.asarray(feet, float).reshape(-1, 2)
        self._teams, self._track_team = det_teams, track_team
        out = super().update(results, img, feats, **kwargs)
        if self._feet is not None:
            for t in self.tracked_stracks:
                if t.frame_id == self.frame_id:
                    f = self._feet[int(t.idx)]
                    if np.isfinite(f).all():
                        t.last_foot = (float(f[0]), float(f[1]))
        return out

    def multi_predict(self, tracks):
        half_life = self.link['decay_half_life']
        if half_life:
            factor = 0.5 ** ((1.0 / self.fps) / half_life)
            for t in tracks:
                if t.state != TrackState.Tracked:
                    t.mean = t.mean.copy()
                    t.mean[4:6] *= factor
        super().multi_predict(tracks)

    def get_dists(self, tracks, detections):
        dists = super().get_dists(tracks, detections)
        if self.link['team_gate'] and len(tracks) and len(detections):
            dists = np.array(dists, dtype=float)
            for i, t in enumerate(tracks):
                if t.state == TrackState.Lost:
                    for j, d in enumerate(detections):
                        if self._conflict(t, d):
                            dists[i, j] = 1.0
        return dists

    def _post_first_association(self, strack_pool, detections, u_track, u_detection, activated, refind):
        if not self.link['pitch_link'] or self._feet is None:
            return u_track, u_detection
        lost = [i for i in u_track if strack_pool[i].state == TrackState.Lost]
        if not lost or not len(u_detection):
            return u_track, u_detection
        left = list(u_detection)
        cost = self._cost([strack_pool[i] for i in lost], [detections[j] for j in left])
        pairs = mutual_nearest(cost, self.link['margin']) if self.link['revive'] else assign(cost)
        used_t, used_d = set(), set()
        for a, b in pairs:
            self._link(strack_pool[lost[a]], detections[left[b]], 'pitch', cost[a, b], refind)
            used_t.add(lost[a])
            used_d.add(left[b])
        return [i for i in u_track if i not in used_t], [j for j in u_detection if j not in used_d]

    def _init_new_tracks(self, u_detection, detections, activated, refind=None):
        if self.link['revive'] and self._feet is not None and refind is not None:
            new = [j for j in u_detection if detections[j].score >= self.args.new_track_thresh]
            lost = [t for t in self.lost_stracks if t.state == TrackState.Lost]
            if new and lost:
                cost = self._cost(lost, [detections[j] for j in new])
                taken = set()
                for a, b in mutual_nearest(cost, self.link['margin']):
                    self._link(lost[a], detections[new[b]], 'revive', cost[a, b], refind)
                    taken.add(new[b])
                u_detection = [j for j in u_detection if j not in taken]
        super()._init_new_tracks(u_detection, detections, activated, refind)
