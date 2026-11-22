"""Football concepts read from player positions in metres: runs in behind, the opponent line stepping up or dropping, wing and central
battles, numbers in the box and set-piece-like stillness.

The definitions follow what tracking-data practice uses: a run in behind attacks the space beyond the last defensive line (SkillCorner,
Driblab), the height of the back line and the compactness near the ball matter for defending (Fujii et al. 2025, Forcher et al. 2024),
and space is judged by who can reach it first (Spearman 2016, Fernandez and Bornn 2018). There is no ball in this data, so nothing here says
who has the ball or who passed; `u` is metres toward the goal the focus team attacks and `y` runs across the pitch.
"""
import math

BOX_DEPTH = 16.5
BOX_HALF_WIDTH = 20.16
RUN_SPEED = 3.0            # m/s along u that makes a run (a jog is about 2-3, a sprint above 6); measured paths are noisy, so the bar is not set higher
LINE_MOVE = 6.0            # metres the back line must change within LINE_SECONDS to be called a step up or a drop
LINE_SECONDS = 8


def runs_in_behind(paths, back_line, fps=5.0, window=4.0, margin=0.0, minimum_share=0.8):
    """Players that ran past the opponent back line.

    paths: {track id: [(frame, u, y)]} sorted by frame (u toward the goal attacked); back_line: {second: u of the opponent back line}.
    A run is a stretch of `window` seconds in which the player moves toward the goal faster than RUN_SPEED on average, starts at least `margin`
    metres in front of the back line and ends at least `margin` metres beyond it. A stretch needs a sighting in `minimum_share` of its frames.
    Returns [{'track', 'start', 'end', 'speed', 'end_u', 'end_y'}] (seconds from the first frame), at least `window` seconds apart per player."""
    runs = []
    length = int(window * fps)
    for tid, path in paths.items():
        by_frame = {f: (u, y) for f, u, y in path}
        last_end = -10 ** 9
        for f0 in sorted(by_frame):
            f1 = f0 + length
            if f0 < last_end + length or f1 not in by_frame:
                continue
            seen = sum(1 for f in range(f0, f1 + 1) if f in by_frame)
            if seen < minimum_share * (length + 1):
                continue
            (u0, _), (u1, y1) = by_frame[f0], by_frame[f1]
            line0, line1 = back_line.get(int(f0 / fps)), back_line.get(int(f1 / fps))
            if line0 is None or line1 is None:
                continue
            speed = (u1 - u0) / window
            if speed >= RUN_SPEED and u0 <= line0 - margin and u1 >= line1 + margin:
                runs.append({'track': tid, 'start': f0 / fps, 'end': f1 / fps, 'speed': round(speed, 1), 'end_u': round(u1, 1), 'end_y': round(y1, 1)})
                last_end = f1
    return sorted(runs, key=lambda r: r['start'])


def line_change(back_line, start, end):
    """'step_up' when the opponent back line moved at least LINE_MOVE metres toward midfield within LINE_SECONDS inside [start, end) seconds,
    'drop' when it moved that far toward its own goal, otherwise None. back_line: {second: u of the opponent back line}."""
    seconds = sorted(s for s in back_line if start <= s < end)
    found = None
    for s in seconds:
        later = [t for t in range(s + 1, s + LINE_SECONDS + 1) if t in back_line and t < end]
        for t in later:
            change = back_line[t] - back_line[s]
            if change <= -LINE_MOVE:
                return 'step_up'
            if change >= LINE_MOVE:
                found = 'drop'
    return found


def zone_of(y, pitch_width=62.0):
    """'wing' near the touchlines, 'half_space' between wing and centre, 'centre' in the middle (y in metres across the pitch)."""
    edge = abs(y) / (pitch_width / 2)
    return 'wing' if edge >= 0.62 else 'half_space' if edge >= 0.26 else 'centre'


def local_balance(ours, theirs, focus, radius=18.0, pitch_width=62.0):
    """Numbers around a place: ours / theirs are [(x, y)] players, focus is (x, y). Returns {'zone', 'ours', 'theirs'} for the players within
    `radius` metres of the focus; the zone is where the focus stands."""
    near = lambda pts: sum(1 for x, y in pts if math.hypot(x - focus[0], y - focus[1]) <= radius)
    return {'zone': zone_of(focus[1], pitch_width), 'ours': near(ours), 'theirs': near(theirs)}


def box_presence(ours, theirs, pitch_length=89.0):
    """Players inside the penalty area of the goal attacked. ours / theirs are [(u, y)]."""
    inside = lambda pts: sum(1 for u, y in pts if u >= pitch_length / 2 - BOX_DEPTH and abs(y) <= BOX_HALF_WIDTH)
    return {'ours': inside(ours), 'theirs': inside(theirs)}


def standing_still(paths_by_frame, first, last, pitch_length=89.0, fps=5.0, seconds=3.0, speed=1.2, minimum=6):
    """True when, for `seconds`, at least `minimum` players are in the penalty area of the goal attacked and almost nobody moves: the picture of a
    corner or a free kick. paths_by_frame: {frame: [(track, u, y)]} of both teams."""
    length = int(seconds * fps)
    for f0 in range(first, last - length + 1):
        inside = {t for t, u, y in paths_by_frame.get(f0, []) if u >= pitch_length / 2 - BOX_DEPTH - 4 and abs(y) <= BOX_HALF_WIDTH + 4}
        if len(inside) < minimum:
            continue
        still = 0
        for t in inside:
            first_pos = next(((u, y) for tid, u, y in paths_by_frame.get(f0, []) if tid == t), None)
            last_pos = next(((u, y) for tid, u, y in paths_by_frame.get(f0 + length, []) if tid == t), None)
            if first_pos and last_pos and math.hypot(first_pos[0] - last_pos[0], first_pos[1] - last_pos[1]) / seconds <= speed:
                still += 1
        if still >= minimum:
            return True
    return False
