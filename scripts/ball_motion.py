"""Find a ball that rolls or flies in a fixed camera with classic image steps (no training): small white blobs on the pitch that are not part of the static picture,
linked over time into a path.

Why: the learned finder (scripts/ball_finder.py, trained on the night match of 2026-11-11) found nothing in the footage of 2026-11-18 (another camera, daylight).
Here the ball is a white blob of about 5 to 12 pixels. Steps per clip of N frames (10 per second):
  1. white mask (bright, little colour) inside the pitch (the calibration maps the pitch outline into the picture);
  2. static white (lines, boots lying still) = pixels white in more than half of the frames of the clip, widened by 2 pixels, is removed;
  3. blobs of 4 to 90 pixels with a plain shape are candidates;
  4. the best chain of candidates that moves plausibly (at most MAX_STEP pixels per frame, small turns) is the ball path; chains shorter than MIN_CHAIN frames are dropped.
A frame without an answer means not found. A ball at a player's feet inside a crowd, or a ball on a line, is often lost. Positions in metres are right only for a ball on the ground.
"""
import math

import cv2
import numpy as np

MAX_STEP = 70.0        # pixels per frame at 10 frames per second (about 30 m/s near the camera)
MIN_CHAIN = 6
MAX_GAP = 2


def pitch_mask(shape, fitted, margin=1.0):
    """Mask of the pitch (plus margin metres) in the picture, from the inverse of the calibration."""
    h, w = shape[:2]
    inv = np.linalg.inv(fitted['H'])
    half_l, half_w = fitted['pitch']['length'] / 2 + margin, fitted['pitch']['width'] / 2 + margin
    pts = []
    for u, v in ((-half_l, -half_w), (half_l, -half_w), (half_l, half_w), (-half_l, half_w)):
        p = inv @ np.array([u, v, 1.0])
        pts.append((p[0] / p[2] * w, p[1] / p[2] * h))
    mask = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(mask, np.array(pts, np.int32), 255)
    return mask


def white_masks(images, mask):
    out = []
    for im in images:
        hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
        m = ((hsv[:, :, 2] > 170) & (hsv[:, :, 1] < 80)).astype(np.uint8) * 255
        out.append(cv2.bitwise_and(m, mask))
    return out


def candidates(images, mask, loose=False):
    """Small bright round blobs: white top-hat of the brightness (lighter than a 13-pixel neighbourhood), little colour, a plain round shape.
    loose=True keeps blobs of 3 to 90 pixels and every shape that is not a line (for a learned ranking afterwards); the score is the top-hat strength."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    frames = []
    for im in images:
        hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
        v = hsv[:, :, 2]
        tophat = cv2.morphologyEx(v, cv2.MORPH_TOPHAT, kernel)
        m = ((tophat > 40) & (hsv[:, :, 1] < 75) & (v > 150)).astype(np.uint8) * 255
        m = cv2.bitwise_and(m, mask)
        n, labels, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=8)
        found = []
        for k in range(1, n):
            x, y, bw, bh, area = stats[k]
            if loose:
                if not (3 <= area <= 90) or bw > 16 or bh > 16 or max(bw, bh) / float(max(1, min(bw, bh))) > 3.0:
                    continue
                peak = float(tophat[y:y + bh, x:x + bw].max())
                found.append((float(cent[k][0]), float(cent[k][1]), min(1.0, peak / 255.0)))
                continue
            if not (5 <= area <= 80) or bw > 14 or bh > 14 or bw < 3 or bh < 3:
                continue
            fill = area / float(bw * bh)
            if fill < 0.5 or max(bw, bh) / float(min(bw, bh)) > 1.8:
                continue
            found.append((float(cent[k][0]), float(cent[k][1]), min(1.0, area / 40.0) * fill))
        frames.append(found)
    return frames


def link(frames):
    """Best chain: maximise the sum of candidate values minus a cost for the jump and for sudden turns. Returns {frame index: (x, y, value)}."""
    n = len(frames)
    best = [[0.0] * len(f) for f in frames]
    back = [[None] * len(f) for f in frames]
    for t in range(n):
        for i, (x, y, s) in enumerate(frames[t]):
            best[t][i] = s
            for g in range(1, MAX_GAP + 2):
                if t - g < 0:
                    break
                for j, (px, py, ps) in enumerate(frames[t - g]):
                    d = math.hypot(x - px, y - py)
                    if d > MAX_STEP * g:
                        continue
                    cost = 0.004 * d / g
                    if back[t - g][j] is not None:
                        bt, bj = back[t - g][j]
                        qx, qy = frames[bt][bj][0], frames[bt][bj][1]
                        v0 = (px - qx, py - qy)
                        v1 = (x - px, y - py)
                        if math.hypot(*v0) > 3 and math.hypot(*v1) > 3:
                            cos = (v0[0] * v1[0] + v0[1] * v1[1]) / (math.hypot(*v0) * math.hypot(*v1))
                            cost += 0.15 * (1 - cos)
                    value = best[t - g][j] + s - cost - 0.05 * (g - 1)
                    if value > best[t][i]:
                        best[t][i], back[t][i] = value, (t - g, j)
    chains = []
    used = set()
    order = sorted(((best[t][i], t, i) for t in range(n) for i in range(len(frames[t]))), reverse=True)
    for value, t, i in order:
        if (t, i) in used:
            continue
        chain, cur = [], (t, i)
        while cur is not None and cur not in used:
            chain.append(cur)
            cur = back[cur[0]][cur[1]]
        if len(chain) >= MIN_CHAIN:
            for c in chain:
                used.add(c)
            chains.append(sorted(chain))
        if len(chains) >= 4:
            break
    path = {}
    for chain in chains:
        for t, i in chain:
            x, y, s = frames[t][i]
            path[t] = (x, y, s)
    return path


def drop_static(frames, radius=3.0, share=0.35):
    """Candidates that sit at the same spot in more than `share` of the frames are part of the picture (a spot mark, a bag, a boot lying still), not a rolling ball."""
    flat = [(x, y) for f in frames for x, y, _ in f]
    if not flat:
        return frames
    arr = np.array(flat)
    out = []
    for f in frames:
        keep = []
        for x, y, sc in f:
            near = np.sum((np.abs(arr[:, 0] - x) <= radius) & (np.abs(arr[:, 1] - y) <= radius))
            if near / float(len(frames)) <= share:
                keep.append((x, y, sc))
        out.append(keep)
    return out


def find_ball(images, fitted):
    mask = pitch_mask(images[0].shape, fitted)
    frames = drop_static(candidates(images, mask))
    return link(frames), frames
