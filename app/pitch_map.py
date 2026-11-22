"""From a saved pitch calibration to positions in metres (the Python twin of web/minimap.js).

The calibration comes from landmark points a person clicked in the reference frame of one camera setting. The pitch
size is an estimate, so every distance has the same unknown scale error. A calibration whose own error is above
MAX_RMS metres is refused, and people who land outside the pitch (plus a margin of 2 m) are not drawn.
Frames of a clip are assumed to share the reference frame's pixel grid (a fixed camera); that is an assumption and
should be checked with `frame_shift` before the numbers are trusted.
"""
import math

import numpy as np

DEFAULTS = {'length': 105.0, 'width': 68.0, 'circle_r': 9.15, 'goal_width': 7.32, 'pa_depth': 16.5, 'pa_width': 40.3,
            'ga_depth': 5.5, 'ga_width': 18.3}
MAX_RMS = 5.0              # metres of calibration error above which nothing is drawn
PITCH_MARGIN = 2.0         # metres outside the lines that are still accepted (people on the running track just beyond the far line sit 2 m or more outside)


def landmarks(d=None):
    """Landmark id -> (X, Y) in metres. X runs along the length (left negative), Y across the width (near touchline positive)."""
    d = {**DEFAULTS, **(d or {})}
    out = {'center': (0.0, 0.0), 'half_near': (0.0, d['width'] / 2), 'half_far': (0.0, -d['width'] / 2),
           'circle_left': (-d['circle_r'], 0.0), 'circle_right': (d['circle_r'], 0.0),
           'circle_near': (0.0, d['circle_r']), 'circle_far': (0.0, -d['circle_r'])}
    half = d['length'] / 2
    for side, sx in (('l', -1), ('r', 1)):
        for near, sy in (('near', 1), ('far', -1)):
            out[f'corner_{side}_{near}'] = (sx * half, sy * d['width'] / 2)
            out[f'post_{side}_{near}'] = (sx * half, sy * d['goal_width'] / 2)
            out[f'pa_{side}_{near}'] = (sx * (half - d['pa_depth']), sy * d['pa_width'] / 2)
            out[f'pa_goalline_{side}_{near}'] = (sx * half, sy * d['pa_width'] / 2)
            out[f'ga_{side}_{near}'] = (sx * (half - d['ga_depth']), sy * d['ga_width'] / 2)
            out[f'ga_goalline_{side}_{near}'] = (sx * half, sy * d['ga_width'] / 2)
    return out


def pitch_lines(d=None):
    d = {**DEFAULTS, **(d or {})}
    half, wide = d['length'] / 2, d['width'] / 2
    lines = [[(-half, -wide), (half, -wide), (half, wide), (-half, wide), (-half, -wide)], [(0, -wide), (0, wide)]]
    lines.append([(d['circle_r'] * math.cos(i / 48 * 2 * math.pi), d['circle_r'] * math.sin(i / 48 * 2 * math.pi)) for i in range(49)])
    for sx in (-1, 1):
        pd, gd = half - d['pa_depth'], half - d['ga_depth']
        lines.append([(sx * half, -d['pa_width'] / 2), (sx * pd, -d['pa_width'] / 2), (sx * pd, d['pa_width'] / 2), (sx * half, d['pa_width'] / 2)])
        lines.append([(sx * half, -d['ga_width'] / 2), (sx * gd, -d['ga_width'] / 2), (sx * gd, d['ga_width'] / 2), (sx * half, d['ga_width'] / 2)])
    return lines


def solve_homography(pairs):
    """Least squares homography from (u, v, X, Y) tuples with at least four points; None when degenerate."""
    rows, rhs = [], []
    for u, v, x, y in pairs:
        rows.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); rhs.append(x)
        rows.append([0, 0, 0, u, v, 1, -u * y, -v * y]); rhs.append(y)
    if len(pairs) < 4:
        return None
    a, b = np.array(rows, float), np.array(rhs, float)
    try:
        h, _, rank, _ = np.linalg.lstsq(a, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if rank < 8:
        return None
    return np.append(h, 1.0).reshape(3, 3)


def apply(h, u, v):
    """Metres of one normalized reference-frame point, or None when the point is behind the camera."""
    w = h[2, 0] * u + h[2, 1] * v + h[2, 2]
    if not w or w <= 0:
        return None
    return ((h[0, 0] * u + h[0, 1] * v + h[0, 2]) / w, (h[1, 0] * u + h[1, 1] * v + h[1, 2]) / w)


def fit(record):
    """record: one entry of calibrations.json. Returns {'H', 'rms', 'errors', 'pitch'} or {'error': reason}."""
    pitch = {**DEFAULTS, **(record.get('pitch') or {})}
    known = landmarks(pitch)
    pairs = [(p['x'], p['y'], *known[p['landmark']]) for p in record.get('points', []) if p.get('landmark') in known]
    h = solve_homography(pairs)
    if h is None:
        return {'error': 'fewer than four usable landmarks, or they lie almost on one line'}
    # A homography and its negative are the same mapping. With the last entry fixed to 1 the scale factor w of the
    # clicked points is often negative (the image corner lies above the horizon), so choose the sign that makes it positive.
    if sum(h[2, 0] * u + h[2, 1] * v + h[2, 2] for u, v, _, _ in pairs) < 0:
        h = -h
    errors = []
    for u, v, x, y in pairs:
        r = apply(h, u, v)
        errors.append(math.hypot(r[0] - x, r[1] - y) if r else float('nan'))
    rms = math.sqrt(sum(e * e for e in errors) / len(errors)) if all(math.isfinite(e) for e in errors) else float('inf')
    if not math.isfinite(rms):
        return {'error': 'a clicked point lies behind the camera in the fitted model'}
    if rms > MAX_RMS:
        return {'error': f'calibration error {rms:.1f} m is above {MAX_RMS:.0f} m; positions would look confident but be wrong', 'rms': rms}
    return {'H': h, 'rms': rms, 'errors': errors, 'pitch': pitch, 'points': len(pairs)}


def feet_to_metres(fitted, box, width, height, shift=(0.0, 0.0), bg=None, margin=PITCH_MARGIN):
    """Metres of the feet (bottom centre) of a pixel box, or None when outside the pitch plus its margin.

    The calibration clicks live in the reference frame of the camera setting. A clip frame is first moved back onto the
    photo the clicks were made on (shift: how far the content of this frame lies from the same content in that photo,
    see frame_shift), and that photo is then mapped to the reference frame with bg = (a, b, tx, ty), the small
    similarity transform the review server stores for every scene (x' = a x - b y + tx, y' = b x + a y + ty).
    """
    x, y = (box[0] + box[2]) / 2 - shift[0], box[3] - shift[1]
    if bg:
        a, b, tx, ty = bg
        x, y = a * x - b * y + tx, b * x + a * y + ty
    m = apply(fitted['H'], x / width, y / height)
    if m is None:
        return None
    pitch = fitted['pitch']
    if abs(m[0]) > pitch['length'] / 2 + margin or abs(m[1]) > pitch['width'] / 2 + margin:
        return None
    return m


def _hull_area(points):
    pts = sorted(points)
    if len(pts) < 3:
        return 0.0
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    ring = lower[:-1] + upper[:-1]
    return abs(sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring)))) / 2


FAR_FROM_TEAM = 30.0       # metres from the coordinate-wise median of the team; a goalkeeper or a distant person is left out


def core_points(points, max_distance=FAR_FROM_TEAM):
    """Players near the middle of their team. Goalkeepers and people far from everyone else would otherwise
    stretch the depth, width and area of the team. This is a distance rule, not a check of who is a goalkeeper."""
    if len(points) < 4:
        return list(points)
    xs, ys = sorted(p[0] for p in points), sorted(p[1] for p in points)
    mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
    return [p for p in points if math.hypot(p[0] - mx, p[1] - my) <= max_distance]


def team_shape(points):
    """Centre, depth (along the length), width (across), hull area and mean nearest-teammate distance, in metres,
    of the players near the middle of the team (see core_points); `left_out` counts the others.
    Needs at least four such players; otherwise None, never a guess."""
    core = core_points(points)
    if len(core) < 4:
        return None
    xs, ys = [p[0] for p in core], [p[1] for p in core]
    nearest = [min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in core if q is not p) for p in core]
    return {'players': len(core), 'left_out': len(points) - len(core), 'centre_x': round(sum(xs) / len(xs), 1), 'centre_y': round(sum(ys) / len(ys), 1),
            'depth': round(max(xs) - min(xs), 1), 'width': round(max(ys) - min(ys), 1), 'area': round(_hull_area(core)),
            'nearest_teammate': round(sum(nearest) / len(nearest), 1)}


def frame_shift(reference_gray, frame_gray):
    """Pixel shift (dx, dy) of a clip frame against the reference frame by phase correlation (cv2); a fixed camera gives about 0.

    A point at (x, y) in the reference frame appears at (x + dx, y + dy) in the clip frame."""
    import cv2
    shift, _ = cv2.phaseCorrelate(np.float32(reference_gray), np.float32(frame_gray))
    return shift


def frame_shift_images(reference_bgr, frame_bgr):
    """frame_shift of two colour images, measured on the lower part of the picture where the pitch is (full resolution pixels)."""
    import cv2

    def prepare(image):
        height = image.shape[0]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)[int(height * .55):int(height * .95), :]
        gray = cv2.GaussianBlur(cv2.resize(gray, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA).astype(np.float32), (0, 0), 2)
        return gray * cv2.createHanningWindow((gray.shape[1], gray.shape[0]), cv2.CV_32F)
    dx, dy = frame_shift(prepare(reference_bgr), prepare(frame_bgr))
    return (dx * 2, dy * 2)
