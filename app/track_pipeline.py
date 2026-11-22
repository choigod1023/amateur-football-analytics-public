"""From raw tracker output to labelled person tracks: labels, joins, short-track removal and marked gap filling.

Used by scripts/track_from_cache.py. Positions are pixels; labels come from a classifier's per-box probabilities.
"""
import numpy as np

from app.team_role_infer import track_label, windowed_labels
from app.track_stitch import drop_duplicates, fill_gaps, stitch_tracks
from app.track_vote import drop_short_tracks, is_person_track, summarise_tracks


def _overlap(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    inter = width * height
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def backfill_births(tracks, class_scores, neon_shares, detections, probabilities_of, neon_of, max_frames=3, min_iou=0.5):
    """The tracker reports a new track only from its second frame on, so the detection that created it is lost. This adds
    it back: for the first row of every track, a detection of the frame before that overlaps the row by at least `min_iou`
    and is not already used by another row of that frame becomes the new first row (up to `max_frames` frames back).
    detections: {frame: [(box, feature row)]}; probabilities_of(feature rows) -> class probabilities; neon_of(feature row) -> neon share.
    Returns the number of rows added."""
    used = {}
    for rows in tracks.values():
        for frame, box in rows:
            used.setdefault(frame, []).append(box)
    added = 0
    for tid in list(tracks):
        for _ in range(max_frames):
            frame, box = tracks[tid][0]
            if frame <= 0:
                break
            best, best_iou = None, min_iou
            for candidate in detections.get(frame - 1, []):
                share = _overlap(box, candidate[0])
                if share >= best_iou and all(_overlap(candidate[0], other) < 0.9 for other in used.get(frame - 1, [])):
                    best, best_iou = candidate, share
            if best is None:
                break
            tracks[tid].insert(0, (frame - 1, [float(v) for v in best[0]]))
            class_scores[tid].insert(0, probabilities_of([best[1]])[0])
            neon_shares[tid].insert(0, neon_of(best[1]))
            used.setdefault(frame - 1, []).append(best[0])
            added += 1
    return added


def enforce_team_size(rows_by_id, class_scores, classes, team_size):
    """No team can have more than `team_size` players on the pitch, so in a frame that shows more, the rows whose label is
    least certain (smallest probability lead over the other team) are handed to the other team when that team has room and
    the box is at least somewhat likely to belong to it, and are left unlabelled otherwise. Returns the number of rows changed."""
    a_index, b_index = classes.index('team_a'), classes.index('team_b')
    by_frame = {}
    for tid, rows in rows_by_id.items():
        for k, row in enumerate(rows):
            if row['team'] in ('A', 'B'):
                by_frame.setdefault(row['frame'], []).append((tid, k))
    changed = 0
    for items in by_frame.values():
        for team, own, other_team, other in (('A', a_index, 'B', b_index), ('B', b_index, 'A', a_index)):
            members = [(t, k) for t, k in items if rows_by_id[t][k]['team'] == team]
            over = len(members) - team_size
            if over <= 0:
                continue
            members.sort(key=lambda m: class_scores[m[0]][m[1]][own] - class_scores[m[0]][m[1]][other])
            for t, k in members[:over]:
                room = sum(1 for tt, kk in items if rows_by_id[tt][kk]['team'] == other_team) < team_size
                rows_by_id[t][k]['team'] = other_team if room and class_scores[t][k][other] >= 0.2 else None
                changed += 1
    return changed


def cap_team_rows(tracks, team_size):
    """After gap filling a team can again show more than `team_size` players in a frame. In such a frame the added (interpolated)
    rows go first, then the rows of the shortest tracks. Returns (new tracks, number of rows dropped)."""
    lengths = {tid: len(rows) for tid, rows in tracks.items()}
    by_frame = {}
    for tid, rows in tracks.items():
        for row in rows:
            if row['team'] in ('A', 'B'):
                by_frame.setdefault((row['frame'], row['team']), []).append((tid, row))
    drop = set()
    for (frame, _), items in by_frame.items():
        over = len(items) - team_size
        if over > 0:
            for tid, _row in sorted(items, key=lambda it: (not it[1].get('interpolated'), lengths[it[0]]))[:over]:
                drop.add((tid, frame))
    result = {}
    for tid, rows in tracks.items():
        kept = [row for row in rows if (tid, row['frame']) not in drop]
        if kept:
            result[tid] = kept
    return result, len(drop)


def finalize_tracks(tracks, class_scores, neon_shares, classes, frame_count, label_window=0, min_track_length=1, fill_gap_frames=0, team_size=None, stitch_gap=8, stitch_overlap=0, *, guarded_stitch=False):
    """tracks: {id: [(frame, [x1, y1, x2, y2]), ...]}; class_scores / neon_shares: {id: [probabilities / neon share per row]}.

    Returns {'tracks': {id: [{'frame', 'team', 'box'[, 'interpolated']}]}, 'joins', 'interpolated_rows', 'summary'}.
    With label_window > 0 every row is labelled from the probabilities of the rows around it, otherwise every track gets one
    label from all of its rows. Tracks that are not people on the pitch (label S) are returned unchanged.
    """
    rows_by_id = {}
    for tid, rows in tracks.items():
        scores, neon = class_scores[tid], neon_shares[tid]
        if label_window:
            labels = windowed_labels(scores, neon, classes, label_window)
        else:
            labels = [track_label(scores, classes, neon=float(np.mean(neon)))] * len(rows)
        rows_by_id[tid] = [{'frame': int(frame), 'team': label, 'box': [round(float(v), 1) for v in box]} for (frame, box), label in zip(rows, labels)]
    capped = enforce_team_size(rows_by_id, class_scores, classes, team_size) if team_size else 0
    people = {tid: rows for tid, rows in rows_by_id.items() if is_person_track(row['team'] for row in rows)}
    stands = {tid: rows for tid, rows in rows_by_id.items() if tid not in people}
    joined, joins = stitch_tracks(people, stitch_gap, stitch_overlap, require_mutual=guarded_stitch,
                                 endpoint_evidence=guarded_stitch, endpoint_team_guard=guarded_stitch)
    joined = drop_short_tracks(joined, min_track_length)
    interpolated = 0
    if fill_gap_frames:
        joined, interpolated = fill_gaps(joined, fill_gap_frames, avoid_covered=fill_gap_frames > 8)
        if fill_gap_frames > 8:
            joined, _ = drop_duplicates(joined)
            if team_size:
                joined, _ = cap_team_rows(joined, team_size)
    everything = {**joined, **stands}
    summary = summarise_tracks({tid: [(r['frame'], r['team']) for r in rows] for tid, rows in joined.items()}, frame_count)
    return {'tracks': everything, 'joins': joins, 'interpolated_rows': interpolated, 'rows_capped_by_team_size': capped, 'summary': summary}
