"""A short forecast of the passing lanes: will a lane that is open now still be open in a second or two?

Every player is moved forward in a straight line with the speed measured over the last second (capped at MAX_SPEED against measurement noise), then the same test as in
app.attack_options (no opponent within LANE_CLEAR metres of the line of the pass) is run on the forecast positions. It is a physics-free baseline: it does not know about
the ball, the pass or what the players want, and a player who turns is predicted wrongly. scripts/evaluate_lane_prediction.py measures on recorded matches whether it
beats the plain assumption that a lane stays as it is.
"""
from app.attack_options import LANE_CLEAR, MAX_PASS, segment_distance

MAX_SPEED = 7.0          # m/s: faster than this over one second is tracking noise for these recordings


def positions(by_frame, team, direction, fps, frame, seconds=1.0):
    """{track: ((u, y) now, (du, dy) per second)} of the players of `team` seen at `frame` (u: metres toward the goal attacked) with their velocity over the last `seconds`."""
    now = {t: (x * direction, y) for t, x, y in by_frame.get(frame, {}).get(team, [])}
    back = int(round(seconds * fps))
    out = {}
    for tid, (u, y) in now.items():
        for f in range(frame - back, frame):                      # the oldest sighting inside the window
            earlier = next(((x * direction, yy) for t, x, yy in by_frame.get(f, {}).get(team, []) if t == tid), None)
            if earlier:
                dt = (frame - f) / fps
                du, dy = (u - earlier[0]) / dt, (y - earlier[1]) / dt
                speed = (du * du + dy * dy) ** 0.5
                if speed > MAX_SPEED:
                    du, dy = du * MAX_SPEED / speed, dy * MAX_SPEED / speed
                out[tid] = ((u, y), (du, dy))
                break
        else:
            out[tid] = ((u, y), (0.0, 0.0))
    return out


def moved(entry, seconds):
    (u, y), (du, dy) = entry
    return u + du * seconds, y + dy * seconds


def lane_open(carrier_xy, mate_xy, defenders):
    """(open, clearance in metres) of the lane carrier -> mate against a list of defender (u, y)."""
    if not defenders:
        return True, 99.0
    clear = min(segment_distance(d, carrier_xy, mate_xy) for d in defenders)
    return clear >= LANE_CLEAR, clear


def forecast(by_frame, team, other, direction, fps, frame, carrier, horizon=1.5):
    """The lanes from `carrier` to every teammate within MAX_PASS metres: [{'track', 'open_now', 'open_later', 'clear_now', 'clear_later'}] with `open_later` from the straight-line
    forecast `horizon` seconds ahead. Empty when the carrier is not seen."""
    mine = positions(by_frame, team, direction, fps, frame)
    theirs = positions(by_frame, other, direction, fps, frame)
    if carrier not in mine or not theirs:
        return []
    c_now, c_later = mine[carrier][0], moved(mine[carrier], horizon)
    d_now, d_later = [v[0] for v in theirs.values()], [moved(v, horizon) for v in theirs.values()]
    lanes = []
    for tid, entry in mine.items():
        if tid == carrier:
            continue
        m_now = entry[0]
        length = ((m_now[0] - c_now[0]) ** 2 + (m_now[1] - c_now[1]) ** 2) ** 0.5
        if length > MAX_PASS or length < 4.0:
            continue
        open_now, clear_now = lane_open(c_now, m_now, d_now)
        open_later, clear_later = lane_open(c_later, moved(entry, horizon), d_later)
        lanes.append({'track': tid, 'open_now': open_now, 'open_later': open_later, 'clear_now': round(clear_now, 1), 'clear_later': round(clear_later, 1)})
    return lanes
