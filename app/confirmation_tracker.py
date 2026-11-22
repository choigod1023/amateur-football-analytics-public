"""Confirm repeated detections geometrically without counting confidence twice.

The detection has already passed track_high_thresh. Fusing its score again at
the fixed 0.7 confirmation cost makes scores below 0.3 impossible to confirm,
even at IoU=1. Preserve the original successful assignments. Only impossible
low-score confirmations get a fallback, requiring three consecutive observations.
"""
import numpy as np
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.trackers.utils import matching


class GeometricConfirmation:
    confirmation_iou = .5
    confirmation_margin = .1

    def _unconfirmed_association(self, unconfirmed, u_detection, detections, activated, removed):
        remaining = [detections[i] for i in u_detection]
        accepted_tracks, accepted_detections = set(), set()
        if unconfirmed and remaining:
            original, _, _ = matching.linear_assignment(self.get_dists(unconfirmed, remaining), thresh=.7)
            for i, j in original:
                unconfirmed[i].update(remaining[j], self.frame_id)
                activated.append(unconfirmed[i])
                accepted_tracks.add(int(i))
                accepted_detections.add(int(j))
            overlap = 1. - matching.iou_distance(unconfirmed, remaining)
            for i, row in enumerate(overlap):
                if i in accepted_tracks:
                    continue
                j = int(np.argmax(row))
                value = float(row[j])
                # Require reciprocal, separated best choices on both sides.
                other_row = np.delete(row, j)
                other_col = np.delete(overlap[:, j], i)
                if (j in accepted_detections or remaining[j].score >= .3
                        or value < self.confirmation_iou
                        or int(np.argmax(overlap[:, j])) != i
                        or (len(other_row) and value - float(other_row.max()) < self.confirmation_margin)
                        or (len(other_col) and value - float(other_col.max()) < self.confirmation_margin)):
                    continue
                track = unconfirmed[i]
                hits = getattr(track, 'confirmation_observations', 1) + 1
                track.update(remaining[j], self.frame_id)
                track.confirmation_observations = hits
                track.is_activated = hits >= 3
                activated.append(track)
                accepted_tracks.add(i)
                accepted_detections.add(j)
        for i, track in enumerate(unconfirmed):
            if i not in accepted_tracks:
                track.mark_removed()
                removed.append(track)
        return [j for j in range(len(remaining)) if j not in accepted_detections], remaining


class ConfirmingBYTETracker(GeometricConfirmation, BYTETracker):
    pass


def with_geometric_confirmation(base):
    """Compose with the existing XYAH camera tracker without replacing its GMC."""
    return type('Confirming' + base.__name__, (GeometricConfirmation, base), {})
