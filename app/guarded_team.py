"""Optional conservative pixel-support classifier for one grey and one coloured kit.

It is an experiment, not a learned model or a guarantee of team identity.
"""
import cv2
import numpy as np


def classify_guarded(frame, box, refs):
    if not all(t in refs for t in ('home', 'away')):
        return 'unknown'
    low = [t for t in ('home', 'away') if refs[t][1] <= 55]
    high = [t for t in ('home', 'away') if refs[t][1] >= 70]
    if len(low) != 1 or len(high) != 1 or low[0] == high[0]:
        return 'unknown'
    x1, y1, x2, y2 = map(int, box)
    h, w = frame.shape[:2]
    # Clipped people and out-of-frame boxes do not contain a reliable shirt
    # region; truncated and negative NumPy slices can otherwise look valid.
    if x1 < 0 or y1 < 0 or x2 > w or y2 > h or x2 <= x1 or y2 <= y1:
        return 'unknown'
    top, bottom = max(0, y1), min(h, y1 + max(1, (y2-y1)//2))
    left, right = max(0, x1), min(w, x2)
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return 'unknown'
    hsv_all = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    valid = hsv_all[:, 2] > 45
    if int(valid.sum()) < max(30, len(hsv_all)//2):
        return 'unknown'
    hsv = hsv_all[valid].astype(float)
    # Reject patches matching adjacent background; this does not establish a
    # segmentation mask or distinguish referees and goalkeepers.
    bw = max(1, x2-x1)
    neighbors = [part.reshape(-1, 3) for part in
                 (frame[top:bottom, max(0, left-bw):left], frame[top:bottom, right:min(w, right+bw)]) if part.size]
    if not neighbors:
        return 'unknown'
    bg = cv2.cvtColor(np.concatenate(neighbors).reshape(1, -1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    bg = bg[bg[:, 2] > 45].astype(float)
    # Without a visible background, distinctiveness cannot be established.
    if len(bg) < 30:
        return 'unknown'

    def supports(pixels):
        distances = []
        for team in (low[0], high[0]):
            h0, s0, v0 = refs[team]
            dh = np.abs(pixels[:, 0]-h0)
            dh = np.minimum(dh, 180-dh)
            weight = np.minimum(pixels[:, 1], s0)/255
            distances.append(np.sqrt((dh*2*weight)**2 + ((pixels[:, 1]-s0)*.30)**2 + ((pixels[:, 2]-v0)*.25)**2))
        d0, d1 = distances
        return (float(np.mean((d0 < 20) & (d0 + 12 < d1))),
                float(np.mean((d1 < 20) & (d1 + 12 < d0))))

    neutral, colour = supports(hsv)
    bg_neutral, bg_colour = supports(bg)
    neutral_distinct = neutral > bg_neutral*1.5 + .01
    colour_distinct = colour > bg_colour*1.5 + .01
    if colour >= .09 and neutral < .10 and colour_distinct:
        return high[0]
    if colour >= .025:
        return 'unknown'
    if neutral >= .50 and neutral_distinct:
        return low[0]
    return 'unknown'
