"""Choose a ball path through per-frame candidate circles, answering only where the evidence is strong.

Input: for every frame a list of (x, y, probability) where the probability comes from some scorer. The path is the
best chain of candidates that move plausibly between frames. Frames outside every accepted chain get no answer
(they are absent from the result), which stands for "unknown", not for "no ball".

Measured once on 8 hand-verified clips with a leave-one-clip-out scorer that used appearance, motion and nearby
people (pixel units, 5 fps): the chains were right on 24 of 106 (cam1) and 27 of 55 (cam3) ball frames, wrong on 2
and 0, and put a ball into 6 of 118 and 5 of 94 frames that show none. The settings were chosen on the same clips,
so real performance is probably lower. The scorer itself is not part of this module.
"""
import math

THRESHOLD = 0.5                 # a candidate below this probability makes a chain worse, not better
DISTANCE_COST = 0.01            # per pixel of movement between two candidates
MAX_SPEED = 150.0               # pixels per frame; faster jumps are not the same ball
MAX_GAP = 2                     # frames that may be skipped inside one chain
MIN_CHAIN = 3                   # shorter chains are not trusted
MIN_VALUE = 0.3                 # total value a chain must reach
MAX_CHAINS = 4                  # the ball may leave the view and return


def link_ball_path(frames, threshold=THRESHOLD, distance_cost=DISTANCE_COST):
    """frames: list (one entry per frame) of [(x, y, probability), ...]. Returns {frame index: (x, y, probability)}."""
    count = len(frames)
    best, back = [], []
    for t in range(count):
        values, links = [], []
        for x, y, p in frames[t]:
            value, link = p - threshold, None
            for earlier in range(max(0, t - MAX_GAP), t):
                for j, (px, py, _) in enumerate(frames[earlier]):
                    distance = math.hypot(x - px, y - py)
                    if distance > MAX_SPEED * (t - earlier):
                        continue
                    candidate = best[earlier][j] + p - threshold - distance_cost * distance
                    if candidate > value:
                        value, link = candidate, (earlier, j)
            values.append(value)
            links.append(link)
        best.append(values)
        back.append(links)
    picks, used = {}, set()
    for _ in range(MAX_CHAINS):
        ends = [(best[t][i], t, i) for t in range(count) for i in range(len(best[t])) if (t, i) not in used]
        if not ends:
            break
        value, t, i = max(ends)
        if value <= MIN_VALUE:
            break
        chain = []
        while (t, i) not in used:
            chain.append((t, i))
            link = back[t][i]
            if link is None:
                break
            t, i = link
        used.update(chain)
        if len(chain) >= MIN_CHAIN:
            for frame, index in chain:
                picks.setdefault(frame, tuple(frames[frame][index]))
    return picks


# Second version: chains are grown at a low probability but kept only when enough members are confident, and a change of
# velocity between three consecutive candidates costs value (a ball does not turn on the spot).
# Measured on 54 hand-verified clips with out-of-fold probabilities from the re-ranker (5 fps):
#   BALANCED: 95.9% of the answers right, 48.1% of the ball frames answered (v1 at 0.7: 95.0% and 39.9%)
#   STRICT:   98.6% right, 38.7% answered (v1 at 0.8: 97.9% and 25.9%)
# The settings were picked on these clips (checked on two clip halves: tuning on one half and testing on the other kept the gain
# for the balanced setting in one direction and lost precision in the other when the low threshold was 0.4, so 0.5 is used).
BALANCED = {'low': 0.5, 'high': 0.9, 'seeds': 3, 'accel': 0.02}
STRICT = {'low': 0.5, 'high': 0.9, 'seeds': 3, 'accel': 0.05}


def link_ball_path_v2(frames, low=0.5, high=0.9, seeds=3, accel=0.02, distance_cost=DISTANCE_COST):
    """frames: list of [(x, y, probability), ...] per frame. Returns {frame index: (x, y, probability)}.
    A chain is accepted when it has at least MIN_CHAIN candidates and at least `seeds` of them reach probability `high`."""
    count = len(frames)
    best, back = [], []
    for t in range(count):
        values, links = [], []
        for x, y, p in frames[t]:
            value, link = p - low, None
            for earlier in range(max(0, t - MAX_GAP), t):
                for j, (px, py, _) in enumerate(frames[earlier]):
                    distance = math.hypot(x - px, y - py)
                    if distance > MAX_SPEED * (t - earlier):
                        continue
                    candidate = best[earlier][j] + p - low - distance_cost * distance
                    if accel and back[earlier][j] is not None:
                        before, k = back[earlier][j]
                        qx, qy, _ = frames[before][k]
                        v0x, v0y = (px - qx) / (earlier - before), (py - qy) / (earlier - before)
                        v1x, v1y = (x - px) / (t - earlier), (y - py) / (t - earlier)
                        candidate -= accel * math.hypot(v1x - v0x, v1y - v0y)
                    if candidate > value:
                        value, link = candidate, (earlier, j)
            values.append(value)
            links.append(link)
        best.append(values)
        back.append(links)
    picks, used = {}, set()
    for _ in range(MAX_CHAINS + 2):
        ends = [(best[t][i], t, i) for t in range(count) for i in range(len(best[t])) if (t, i) not in used]
        if not ends:
            break
        value, t, i = max(ends)
        if value <= MIN_VALUE:
            break
        chain = []
        while (t, i) not in used:
            chain.append((t, i))
            link = back[t][i]
            if link is None:
                break
            t, i = link
        used.update(chain)
        confident = sum(frames[frame][index][2] >= high for frame, index in chain)
        if len(chain) >= MIN_CHAIN and confident >= seeds:
            for frame, index in chain:
                picks.setdefault(frame, tuple(frames[frame][index]))
    return picks
