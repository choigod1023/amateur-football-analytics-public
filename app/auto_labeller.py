"""Automatic judge of 'is this box a person?' for the boxes two person detectors disagree on (research tool, never mixed with human labels).

The judge is trained on the boxes the user judged by hand (person-check sessions). Its output has three levels: accept, reject, ask a human.
Every number it reports comes from cross-validation over time blocks, so frames that are close in time never sit on both sides of a split.
The judge only knows boxes that look like the judged ones (found by one detector only, score 0.35 to 0.45); anything else is sent to a human.
"""
import math

import numpy as np

SCORE_RANGE = (0.35, 0.45)      # the score band the user judged; outside it the judge does not apply
ACCEPT_PRECISION = 0.95         # target share of real people among accepted boxes
REJECT_PRECISION = 0.90         # target share of non-people among rejected boxes
MIN_DECIDED = 8                 # a threshold must decide at least this many judged boxes, otherwise the level stays empty
BASE_FEATURES = ['is_b', 'score', 'log_height', 'aspect', 'y_rel', 'neon', 'dark', 'sharp', 'contrast', 'ring_diff', 'green']
ORIGIN = 'auto_labeller'


def _crop(image, box, pad=0.0):
    h, w = image.shape[:2]
    bw, bh = box[2] - box[0], box[3] - box[1]
    x1, y1 = int(max(0, box[0] - pad * bw)), int(max(0, box[1] - pad * bh))
    x2, y2 = int(min(w, box[2] + pad * bw)) + 1, int(min(h, box[3] + pad * bh)) + 1
    return image[y1:y2, x1:x2]


def box_features(cv2, image, box, score, found_by):
    """One box of a BGR frame -> dict of the BASE_FEATURES (plain numbers)."""
    height, width = image.shape[:2]
    bw, bh = max(1.0, box[2] - box[0]), max(1.0, box[3] - box[1])
    patch = image[int(box[1] + .18 * bh):int(box[1] + .55 * bh) + 1, int(box[0] + .2 * bw):int(box[2] - .2 * bw) + 1]
    neon = dark = 0.0
    if patch.size:
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
        neon = float(((hsv[:, 0] >= 22) & (hsv[:, 0] <= 44) & (hsv[:, 1] > 90) & (hsv[:, 2] > 110)).mean())
        dark = float((hsv[:, 2] < 80).mean())
    crop = _crop(image, box)
    sharp = contrast = 0.0
    green = 0.0
    if crop.size:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sharp = math.log1p(float(cv2.Laplacian(gray, cv2.CV_64F).var())) if min(gray.shape) >= 3 else 0.0
        contrast = float(gray.std())
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
        green = float(((hsv[:, 0] >= 35) & (hsv[:, 0] <= 85) & (hsv[:, 1] > 40)).mean())
    ring_diff = 0.0
    outer = _crop(image, box, pad=0.6)
    if crop.size and outer.size:
        lab_in = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32).mean(axis=0)
        total = cv2.cvtColor(outer, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
        n_in, n_all = crop.shape[0] * crop.shape[1], total.shape[0]
        if n_all > n_in:
            ring = (total.sum(axis=0) - lab_in * n_in) / (n_all - n_in)
            ring_diff = float(np.linalg.norm(lab_in - ring))
    return {'is_b': 1.0 if found_by == 'B' else 0.0, 'score': float(score), 'log_height': math.log(bh), 'aspect': bw / bh,
            'y_rel': ((box[1] + box[3]) / 2) / height, 'neon': neon, 'dark': dark, 'sharp': sharp, 'contrast': contrast,
            'ring_diff': ring_diff, 'green': green}


def time_groups(times, block=120.0):
    """Group ids by time block so that boxes close in time always share a group."""
    return [int(t // block) for t in times]


def group_folds(groups, folds, seed=0):
    """Assign every distinct group to one of `folds` folds (balanced by sample count). Returns a fold number per sample."""
    counts = {}
    for g in groups:
        counts[g] = counts.get(g, 0) + 1
    rng = np.random.RandomState(seed)
    order = sorted(counts, key=lambda g: (-counts[g], rng.rand()))
    load = [0] * folds
    where = {}
    for g in order:
        k = min(range(folds), key=lambda i: load[i])
        where[g] = k
        load[k] += counts[g]
    return [where[g] for g in groups]


def near_any(t, others, seconds=15.0):
    return any(abs(t - o) <= seconds for o in others)


class Ridge:
    """Logistic regression with a ridge penalty on standardised features (plain numpy, Newton steps)."""

    def __init__(self, lam=1.0, steps=40):
        self.lam, self.steps = lam, steps
        self.mean = self.std = self.w = None

    def fit(self, x, y):
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        self.mean = x.mean(axis=0)
        self.std = x.std(axis=0)
        self.std[self.std < 1e-9] = 1.0
        z = np.hstack([np.ones((len(x), 1)), (x - self.mean) / self.std])
        w = np.zeros(z.shape[1])
        penalty = np.eye(z.shape[1]) * self.lam
        penalty[0, 0] = 0.0
        for _ in range(self.steps):
            p = 1 / (1 + np.exp(-np.clip(z @ w, -30, 30)))
            grad = z.T @ (p - y) + penalty @ w
            hess = (z.T * (p * (1 - p) + 1e-6)) @ z + penalty
            step = np.linalg.solve(hess, grad)
            w -= step
            if np.abs(step).max() < 1e-7:
                break
        self.w = w
        return self

    def predict(self, x):
        z = np.hstack([np.ones((len(x), 1)), (np.asarray(x, dtype=np.float64) - self.mean) / self.std])
        return 1 / (1 + np.exp(-np.clip(z @ self.w, -30, 30)))

    def to_json(self):
        return {'lam': self.lam, 'mean': self.mean.tolist(), 'std': self.std.tolist(), 'w': self.w.tolist()}

    @classmethod
    def from_json(cls, data):
        model = cls(data['lam'])
        model.mean, model.std, model.w = np.array(data['mean']), np.array(data['std']), np.array(data['w'])
        return model


def pick_thresholds(prob, label, accept_target=ACCEPT_PRECISION, reject_target=REJECT_PRECISION, minimum=MIN_DECIDED):
    """Out-of-fold probabilities and 0/1 labels -> (accept threshold or None, reject threshold or None).

    The accept threshold is the lowest probability whose boxes at or above it are at least `accept_target` real people and number at least `minimum`;
    the reject threshold is the highest probability whose boxes at or below it are at least `reject_target` non-people and number at least `minimum`.
    A level that cannot reach its target stays empty (None)."""
    prob, label = np.asarray(prob, dtype=float), np.asarray(label, dtype=float)
    hi = lo = None
    for t in sorted(set(prob.tolist())):
        chosen = prob >= t
        if chosen.sum() >= minimum and label[chosen].mean() >= accept_target:
            hi = t
            break
    for t in sorted(set(prob.tolist()), reverse=True):
        chosen = prob <= t
        if chosen.sum() >= minimum and (1 - label[chosen]).mean() >= reject_target:
            lo = t
            break
    return hi, lo


def decide(p, hi, lo):
    """Probability and thresholds -> 'accept', 'reject' or 'ask'."""
    if hi is not None and p >= hi:
        return 'accept'
    if lo is not None and p <= lo:
        return 'reject'
    return 'ask'


def in_scope(score, found_by):
    """The judge applies only to boxes that one detector found alone with a score in SCORE_RANGE."""
    return found_by in ('A', 'B') and SCORE_RANGE[0] <= score <= SCORE_RANGE[1]


def wilson_lower(ok, n, z=1.96):
    """Lower end of the 95 % Wilson interval of ok/n (0 when n is 0)."""
    if n == 0:
        return 0.0
    p = ok / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / d


def oof_probabilities(x, y, groups, lam, folds=4, seed=0):
    """Out-of-fold probabilities by group k-fold."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    fold = np.asarray(group_folds(groups, folds, seed))
    out = np.zeros(len(y))
    for k in range(folds):
        train, test = fold != k, fold == k
        if test.sum() == 0 or len(set(y[train].tolist())) < 2:
            out[test] = y[train].mean() if train.any() else 0.5
            continue
        out[test] = Ridge(lam).fit(x[train], y[train]).predict(x[test])
    return out


def nested_evaluation(x, y, groups, lam, outer=6, inner=4, seed=0, accept_target=ACCEPT_PRECISION):
    """Honest three-level result: thresholds are chosen on the training part of each outer fold only and applied to the held-out part.

    Returns {'prob': held-out probabilities, 'decision': list of 'accept'/'reject'/'ask', 'thresholds': per fold}."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    fold = np.asarray(group_folds(groups, outer, seed))
    prob = np.zeros(len(y))
    decision = ['ask'] * len(y)
    thresholds = []
    for k in range(outer):
        train, test = np.where(fold != k)[0], np.where(fold == k)[0]
        if len(test) == 0:
            continue
        inner_prob = oof_probabilities(x[train], y[train], [groups[i] for i in train], lam, inner, seed)
        hi, lo = pick_thresholds(inner_prob, y[train], accept_target=accept_target)
        thresholds.append((hi, lo))
        model = Ridge(lam).fit(x[train], y[train])
        p = model.predict(x[test])
        for i, pi in zip(test, p):
            prob[i] = pi
            decision[i] = decide(pi, hi, lo)
    return {'prob': prob, 'decision': decision, 'thresholds': thresholds}


def auc(prob, label):
    prob, label = np.asarray(prob, dtype=float), np.asarray(label, dtype=float)
    pos, neg = prob[label == 1], prob[label == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float('nan')
    wins = sum((p > neg).sum() + 0.5 * (p == neg).sum() for p in pos)
    return float(wins / (len(pos) * len(neg)))


def summarise(decision, label):
    """Decisions and 0/1 labels -> counts: accepted (how many were people), rejected (how many were non-people), asked."""
    label = np.asarray(label)
    acc = [i for i, d in enumerate(decision) if d == 'accept']
    rej = [i for i, d in enumerate(decision) if d == 'reject']
    ask = [i for i, d in enumerate(decision) if d == 'ask']
    return {'accept': len(acc), 'accept_people': int(label[acc].sum()) if acc else 0, 'reject': len(rej),
            'reject_nonpeople': int((1 - label[rej]).sum()) if rej else 0, 'ask': len(ask), 'ask_people': int(label[ask].sum()) if ask else 0}
