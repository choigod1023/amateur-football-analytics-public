import numpy as np
import pytest

from app.team_role_infer import predict, track_label, windowed_labels

CLASSES = ['referee', 'spectator', 'team_a', 'team_b']


def test_track_label_uses_the_mean_and_refuses_unclear_tracks():
    clear = [[0.05, 0.05, 0.8, 0.1], [0.1, 0.0, 0.6, 0.3], [0.0, 0.1, 0.7, 0.2]]
    assert track_label(clear, CLASSES) == 'A'
    assert track_label([[0.1, 0.1, 0.4, 0.4]] * 3, CLASSES) is None            # best class below the confidence floor
    assert track_label([[0.0, 0.0, 0.52, 0.48]] * 3, CLASSES) is None          # no clear margin
    assert track_label([], CLASSES) is None
    assert track_label([[0.9, 0.0, 0.05, 0.05]], CLASSES) == 'R'


def test_predict_averages_saved_nets_and_returns_probabilities():
    torch = pytest.importorskip('torch')
    nn = torch.nn
    torch.manual_seed(0)
    nets = [nn.Sequential(nn.Linear(3, 4)) for _ in range(2)]
    model = {'nets': nets, 'mean': np.zeros(3, np.float32), 'spread': np.ones(3, np.float32), 'classes': CLASSES}
    out = predict(model, np.random.default_rng(0).normal(size=(5, 3)))
    assert out.shape == (5, 4) and np.allclose(out.sum(1), 1, atol=1e-5)


def test_an_undecided_track_with_a_neon_vest_goes_to_team_a():
    undecided = [[0.0, 0.0, 0.52, 0.48]] * 4
    assert track_label(undecided, CLASSES) is None
    assert track_label(undecided, CLASSES, neon=0.2) == 'A'
    assert track_label(undecided, CLASSES, neon=0.03) is None                       # no vest: still undecided
    assert track_label([[0.4, 0.0, 0.3, 0.3]] * 3, CLASSES, neon=0.3) is None   # the doubt is not between the two teams
    assert track_label([[0.0, 0.0, 0.1, 0.9]] * 3, CLASSES, neon=0.3) == 'B'       # a clear answer is never overridden


def test_a_window_follows_a_player_switch_that_a_whole_track_label_would_hide():
    a = [0.0, 0.0, 0.9, 0.1]
    b = [0.0, 0.0, 0.1, 0.9]
    rows = [a] * 12 + [b] * 12                                       # the track follows a team A player, then swaps to a team B player
    assert track_label(rows, CLASSES) is None                          # one label for the whole track is undecided
    labels = windowed_labels(rows, [0.0] * 24, CLASSES, half_window=3)
    assert labels[2] == 'A' and labels[21] == 'B'
    assert windowed_labels([], [], CLASSES, 3) == []
