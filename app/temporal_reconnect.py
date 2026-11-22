"""Multi-observation identity scorer with bounded, causal confirmation delay.

No hidden players or detector boxes are synthesized. Scores are not probabilities.
Callers must buffer two analysis frames (0.4 s at 5 Hz) before publishing IDs.
"""
import math
import numpy as np
from .learned_reconnect import FEATURES, descriptor, pair_features, fit_scorer
from .clean_track_history import crowded_ids, invalidate_crowded_history

TEMPORAL_FEATURES = FEATURES + [
    'forward_residual', 'backward_residual', 'velocity_difference',
    'direction_difference', 'appearance_instability',
]


def aggregate(sequence):
    if len(sequence) < 3 or any(r.get('crowded', False) or r['descriptor'] is None for r in sequence):
        return None
    times = np.asarray([r['time'] for r in sequence], float)
    if not np.all(np.diff(times) > 0) or times[-1] - times[0] < .15:
        return None
    boxes = np.asarray([r['box'] for r in sequence], float)
    points = np.column_stack(((boxes[:, 0] + boxes[:, 2]) / 2, boxes[:, 3]))
    # Median pairwise slopes resist a single shaky small-person box.
    slopes = [(points[j] - points[i]) / (times[j] - times[i])
              for i in range(len(times)) for j in range(i + 1, len(times))]
    velocity = np.median(slopes, axis=0)
    appearance = [np.mean([r['descriptor'][c] for r in sequence], axis=0) for c in range(6)]
    spread = np.mean([math.sqrt(max(0., 1 - float(np.sqrt(d * m).sum())))
                      for r in sequence for d, m in zip(r['descriptor'], appearance)])
    return appearance, points, velocity, float(spread)


def sequence_features(before, after):
    a, b = aggregate(before), aggregate(after)
    if a is None or b is None:
        return None
    gap = after[0]['time'] - before[-1]['time']
    if gap <= 0:
        return None
    ba, bb = before[-1]['box'], after[0]['box']
    height = max(1., (ba[3] - ba[1] + bb[3] - bb[1]) / 2)
    basic = pair_features(a[0], b[0], ba, bb, gap)
    forward = np.linalg.norm(a[1][-1] + a[2] * gap - b[1][0]) / height
    backward = np.linalg.norm(b[1][0] - b[2] * gap - a[1][-1]) / height
    speed_a, speed_b = np.linalg.norm(a[2]), np.linalg.norm(b[2])
    direction = 0. if min(speed_a, speed_b) < .1 * height else (
        1 - np.clip(np.dot(a[2], b[2]) / (speed_a * speed_b), -1., 1.)) / 2
    return np.r_[basic, forward, backward, np.linalg.norm(a[2] - b[2]) / height,
                 direction, (a[3] + b[3]) / 2]


def fit_temporal(x, y):
    model = fit_scorer(x, y)
    model['features'] = TEMPORAL_FEATURES
    model['confirmation_frames'] = 3
    model['output_delay_frames'] = 2
    model['max_prediction_residual_heights'] = 1.5
    return model


def temporal_score(model, features):
    if features is None:
        return 0.
    if model['features'] != TEMPORAL_FEATURES:
        raise ValueError('Incompatible temporal feature schema')
    z = (features - np.asarray(model['mean'])) / np.asarray(model['scale'])
    value = float(z @ np.asarray(model['weights']) + model['bias'])
    return 1 / (1 + math.exp(-max(-30., min(30., value))))


class TemporalLinker:
    """Confirm births once at their third consecutive observed analysis frame.

Previously published identities are never revised. Only the two pending frames
    may use the identity confirmed by the current frame.
    """
    def __init__(self, model):
        self.model = model
        self.memory = {}
        self.time = None

    def resolve(self, raw):
        return self.memory.get(raw, {}).get('canonical', raw)

    def update(self, t, frame, tracks):
        if self.time is not None and t <= self.time:
            self.memory = {}
        self.time = t
        self.memory = {k: v for k, v in self.memory.items() if t - v['last'] <= 10}
        current = {str(int(r[4])): r for r in tracks}
        crowded = crowded_ids(current)
        for raw, row in current.items():
            state = self.memory.setdefault(raw, {'first': t, 'last': t, 'canonical': raw,
                                                  'history': [], 'decided': False})
            if raw in crowded:
                invalidate_crowded_history(state, t)
                continue
            obs = {'time': float(t), 'box': list(map(float, row[:4])),
                   'descriptor': descriptor(frame, row[:4])}
            if state['history'] and t - state['last'] > .25:
                # This raw ID already appeared: do not retrospectively alias it.
                state['decided'] = True
            state['history'] = [r for r in state['history'] if t - r['time'] <= 1.01]
            state['history'] = (state['history'] + [obs])[-5:]
            state['last'] = t
        # Raw tracker reactivation beside an alias must not duplicate one player.
        groups = {}
        for raw in current:
            groups.setdefault(self.resolve(raw), []).append(raw)
        for members in groups.values():
            if len(members) > 1:
                for raw in members:
                    self.memory[raw]['canonical'] = raw
        reserved = {self.resolve(k) for k in current}
        proposals = []
        for raw in current:
            state = self.memory[raw]
            if state['decided'] or len(state['history']) < 3:
                continue
            state['decided'] = True
            choices = []
            for old, previous in self.memory.items():
                gap = state['first'] - previous['last']
                if old in current or previous['canonical'] in reserved or not 0 < gap <= 2.5:
                    continue
                features = sequence_features(previous['history'], state['history'])
                if features is None or max(features[9], features[10]) > self.model['max_prediction_residual_heights']:
                    continue
                value = temporal_score(self.model, features)
                choices.append((value, old, previous['canonical']))
            choices.sort(reverse=True)
            # Distinct raw fragments of the same canonical person are one choice.
            unique = {}
            for candidate in choices:
                unique.setdefault(candidate[2], candidate)
            choices = list(unique.values())
            if choices and choices[0][0] >= self.model['threshold'] and (
                    len(choices) == 1 or choices[0][0] - choices[1][0] >= self.model['ambiguity_margin']):
                proposals.append((raw, *choices[0]))
        events = []
        for raw, value, old, canonical in proposals:
            if sum(p[3] == canonical for p in proposals) != 1:
                continue
            self.memory[raw]['canonical'] = canonical
            events.append({'time': float(t), 'birth_time': self.memory[raw]['first'],
                           'raw': raw, 'previous_raw': old, 'canonical': canonical, 'score': float(value)})
        return {raw: self.resolve(raw) for raw in current}, events
