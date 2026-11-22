"""Smooth paths of one tracked player for the video report: a box for every frame (gaps bridged, jitter removed) and the choice of the player to follow."""


def box_path(rows, first, last, max_gap=50, radius=3):
    """rows: [{'frame', 'box'}] of one track. Returns {frame: [x1, y1, x2, y2]} for every frame of first..last that lies between two sightings of the
    track no more than `max_gap` frames apart (a straight line across the gap), smoothed with a moving average of +-`radius` frames."""
    rows = sorted(rows, key=lambda r: r['frame'])
    raw = {}
    for a, b in zip(rows, rows[1:]):
        gap = b['frame'] - a['frame']
        if gap > max_gap:
            continue
        for f in range(max(a['frame'], first), min(b['frame'], last + 1)):
            share = (f - a['frame']) / gap
            raw[f] = [x + (y - x) * share for x, y in zip(a['box'], b['box'])]
    if rows and first <= rows[-1]['frame'] <= last:
        raw[rows[-1]['frame']] = list(rows[-1]['box'])
    smooth = {}
    for f in raw:
        near = [raw[g] for g in range(f - radius, f + radius + 1) if g in raw]
        smooth[f] = [sum(box[i] for box in near) / len(near) for i in range(4)]
    return smooth


def coverage(path, first, last):
    return sum(1 for f in range(first, last + 1) if f in path) / max(1, last - first + 1)


def choose_key_track(tracks, preferred, team, first, last, mean_u, minimum=0.6, accept=None):
    """The track to follow in a scene. The preferred one (as picked from the metrics) when its path covers at least `minimum` of the scene,
    otherwise the track of `team` with enough coverage and the most advanced mean position (mean_u: {track id: metres toward the goal attacked}).
    accept(track id, path) -> bool can veto a track (for example a player whose shirt colour does not match the team)."""
    def path_of(tid):
        return box_path([r for r in tracks.get(str(tid), []) if first - 60 <= r['frame'] <= last + 60], first, last)
    if preferred is not None:
        path = path_of(preferred)
        if coverage(path, first, last) >= minimum and (accept is None or accept(str(preferred), path)):
            return str(preferred), path
    best = None
    for tid, u in mean_u.items():
        rows = [r for r in tracks.get(str(tid), []) if first - 60 <= r['frame'] <= last + 60]
        if not rows or not any(r['team'] == team for r in rows if first <= r['frame'] <= last):
            continue
        path = box_path(rows, first, last)
        height = sum(b[3] - b[1] for b in path.values()) / max(1, len(path))
        if coverage(path, first, last) >= minimum and height >= 22 and (best is None or u > best[0]) and (accept is None or accept(str(tid), path)):
            best = (u, str(tid), path)
    return (best[1], best[2]) if best else (None, {})
