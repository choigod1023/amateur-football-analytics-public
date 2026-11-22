"""Use a model saved by scripts/train_team_role.py on person boxes (inference only).

The model was trained on the labelled scenes of one match, so its answers for another camera setting or match are
unverified. Probabilities of a track are summed over its frames before a label is chosen, and a track whose best class
is not clearly ahead gets no label.
"""
import numpy as np

LETTER = {'team_a': 'A', 'team_b': 'B', 'referee': 'R', 'spectator': 'S'}


def load_model(path):
    import torch
    import torch.nn as nn
    data = torch.load(path, map_location='cpu', weights_only=False)
    nets = []
    for state in data['states']:
        net = nn.Sequential(nn.Linear(len(data['features']), data['hidden']), nn.ReLU(), nn.Dropout(.2), nn.Linear(data['hidden'], len(data['classes'])))
        net.load_state_dict(state)
        net.eval()
        nets.append(net)
    return {'nets': nets, 'mean': np.asarray(data['mean'], np.float32), 'spread': np.asarray(data['spread'], np.float32), 'classes': list(data['classes'])}


def predict(model, features):
    """features: array (n, feature count). Returns class probabilities (n, classes) averaged over the saved nets."""
    import torch
    x = torch.tensor((np.asarray(features, np.float32) - model['mean']) / model['spread'])
    with torch.no_grad():
        probabilities = sum(torch.softmax(net(x), 1).numpy() for net in model['nets']) / len(model['nets'])
    return probabilities


def track_label(probabilities, classes, minimum_confidence=0.5, minimum_margin=0.1, neon=None, neon_floor=0.10):
    """Label letter of one track from the probabilities of its frames, or None when the evidence is not clear.

    neon: the mean neon-vest share of the track's upper body (feature 'neon'), when known. A track whose two best
    classes are team A and team B but whose probabilities are too close to call is given to team A when it
    carries a neon vest (neon >= neon_floor), because the vest is the one reliable sign of team A in this match.
    """
    if len(probabilities) == 0:
        return None
    mean = np.asarray(probabilities, np.float32).mean(0)
    order = np.argsort(mean)[::-1]
    best, second = classes[int(order[0])], classes[int(order[1])]
    if mean[order[0]] >= minimum_confidence and mean[order[0]] - mean[order[1]] >= minimum_margin:
        return LETTER.get(best)
    if neon is not None and neon >= neon_floor and {best, second} == {'team_a', 'team_b'} and mean[order[0]] + mean[order[1]] >= 0.7:
        return 'A'
    return None


def windowed_labels(probabilities, neon_shares, classes, half_window, **kwargs):
    """One label letter per row of a track from the probabilities of the rows around it (half_window rows each side).

    A whole-track label is wrong whenever the tracker swaps two people (a team A and a team B player share one track
    for a while), and a window follows such a switch within a second or two. Extra keyword arguments go to track_label.
    """
    probabilities = np.asarray(probabilities, np.float32)
    labels = []
    for i in range(len(probabilities)):
        lo, hi = max(0, i - half_window), min(len(probabilities), i + half_window + 1)
        neon = float(np.mean(neon_shares[lo:hi])) if len(neon_shares) else None
        labels.append(track_label(probabilities[lo:hi], classes, neon=neon, **kwargs))
    return labels
