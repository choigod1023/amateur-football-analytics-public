"""Reserve strong visible-track matches, then use the original joint association."""
import numpy as np
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.trackers.basetrack import TrackState
from ultralytics.trackers.utils import matching


class ActivePriority:
    def _first_association(self, pool, detections, activated, refind):
        active = [i for i, track in enumerate(pool) if track.state == TrackState.Tracked]
        used_tracks, used_detections = set(), set()
        if active and detections:
            tracks = [pool[i] for i in active]
            overlap = 1. - matching.iou_distance(tracks, detections)
            costs = self.get_dists(tracks, detections)
            for row, values in enumerate(overlap):
                j = int(np.argmax(values))
                value = float(values[j])
                alternatives = np.delete(values, j)
                rivals = np.delete(overlap[:, j], row)
                if (value < .5 or costs[row, j] > self.args.match_thresh
                        or int(np.argmax(overlap[:, j])) != row
                        or (len(alternatives) and value - alternatives.max() < .1)
                        or (len(rivals) and value - rivals.max() < .1)):
                    continue
                i = active[row]
                self._apply_match(pool[i], detections[j], activated, refind)
                used_tracks.add(i)
                used_detections.add(j)
        left = [i for i in range(len(pool)) if i not in used_tracks]
        right = [j for j in range(len(detections)) if j not in used_detections]
        pairs, unmatched, remaining = matching.linear_assignment(
            self.get_dists([pool[i] for i in left], [detections[j] for j in right]),
            thresh=self.args.match_thresh)
        self._apply_matches(pairs, [pool[i] for i in left], [detections[j] for j in right], activated, refind)
        return [left[i] for i in unmatched], [right[j] for j in remaining]


class ActivePriorityBYTETracker(ActivePriority, BYTETracker):
    pass


def with_active_priority(base):
    return type('ActivePriority' + base.__name__, (ActivePriority, base), {})
