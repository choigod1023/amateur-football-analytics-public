"""Conservative observed-box recovery; never generates a synthetic player."""
import math


def iou(a, b):
    intersection = max(0., min(a[2], b[2])-max(a[0], b[0])) * max(0., min(a[3], b[3])-max(a[1], b[1]))
    areas = [(r[2]-r[0])*(r[3]-r[1]) for r in (a,b)]
    return intersection / max(1e-9, sum(areas)-intersection)


def select_recovery_boxes(found, previous, labelled_ids, reliable=.10):
    """Keep all strong boxes; recover only isolated, near-identical weak boxes.

    previous must contain only the immediately preceding tracker observations.
    Occlusion, ambiguous matches and competition with a strong detection veto
    recovery. This intentionally favours precision over recall.
    """
    strong = [d for d in found if d[4] >= reliable]
    accepted = []
    used = set()
    for d in sorted((d for d in found if d[4] < reliable), key=lambda d:d[4], reverse=True):
        if not all(math.isfinite(float(v)) for v in d[:5]):
            continue
        matches = sorted(((iou(d, p), int(p[4]), p) for p in previous), key=lambda x:x[0], reverse=True)
        if not matches or matches[0][0] < .6 or (len(matches)>1 and matches[1][0] > .1):
            continue
        _, tid, old = matches[0]
        if tid not in labelled_ids or tid in used:
            continue
        height = old[3]-old[1]
        if height <= 0 or not .8 <= (d[3]-d[1])/height <= 1.25:
            continue
        if math.hypot((d[0]+d[2]-old[0]-old[2])/2, d[3]-old[3]) > .2*height:
            continue
        if any(iou(d, s) > .1 or iou(old, s) > .1 for s in strong):
            continue
        accepted.append(d)
        used.add(tid)
    return strong + accepted


class RecoveryDisplay:
    """One-sample measured recovery, isolated from tracker/classifier state.

    A weak point never becomes a new anchor. No box means no recovery; no
    current-frame tracking or projection evidence is overwritten.
    """
    def __init__(self):
        self.time = None
        self.previous = []
        self.points = {}

    def update(self, t, found, tracked, displayed, project, pitch, ready=True, reliable=.1):
        current = {p['id']:p for p in displayed if p['x'] is not None and p['y'] is not None}
        previous, old_points, old_time = self.previous, self.points, self.time
        self.previous = [list(r[:5]) for r in tracked if str(int(r[4])) in current] if ready else []
        self.points, self.time = current, t
        if not ready or old_time is None or not 0 < t-old_time <= .25:
            return []
        occupied = {str(int(r[4])) for r in tracked}
        chosen = select_recovery_boxes(found, previous, {int(p) for p in old_points}, reliable)
        result = []
        for box in chosen:
            if box[4] >= reliable:
                continue
            old = max(previous, key=lambda p:iou(box,p))
            tid = str(int(old[4]))
            if tid in occupied:
                continue
            old_point = old_points[tid]
            point = project(box)
            if point is None:
                continue
            nx, ny = .5+point[0]/pitch['length'], .5+point[1]/pitch['width']
            if not (0 <= nx <= 1 and 0 <= ny <= 1):
                continue
            distance = lambda p: math.hypot((nx-p['x'])*pitch['length'], (ny-p['y'])*pitch['width'])
            if distance(old_point) > 12*(t-old_time):
                continue
            if any(distance(p) < .75 for p in [*current.values(),*result]):
                continue
            if sum(p['team']==old_point['team'] for p in [*current.values(),*result]) >= 11:
                continue
            result.append({'id':tid,'team':old_point['team'],'x':nx,'y':ny,
                           'observation_kind':'low_confidence_recovery','detection_confidence':float(box[4])})
        return result
