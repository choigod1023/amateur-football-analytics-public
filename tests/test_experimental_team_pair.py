import numpy as np
import pytest
from app.experimental_team_pair import ExperimentalTeamPair, shirt_histogram


def model():
    return {'weights1': np.zeros((32, 16)).tolist(), 'bias1': np.zeros(32).tolist(),
            'weights2': np.zeros((1, 32)).tolist(), 'bias2': [0], 'margin': .05, 'floor': .45}


def test_unknown_role_and_ambiguous_scores_are_not_assigned():
    support = {'home': [[1.] * 16] * 3, 'away': [[0.] * 16] * 3}
    clf = ExperimentalTeamPair(model(), support)
    img = np.full((100, 100, 3), 180, dtype=np.uint8)
    assert clf.classify(img, (10, 10, 40, 70)) == 'unknown'
    assert clf.classify(img, (10, 10, 40, 70), role='referee') == 'unknown'
    assert clf.classify(img, (10, 10, 40, 70), role='player') == 'unknown'
    assert shirt_histogram(img, (-1, 0, 20, 50)) is None


def test_invalid_weights_or_reference_are_rejected():
    with pytest.raises(ValueError):
        ExperimentalTeamPair(model(), {'home': [[0.] * 16], 'away': [[0.] * 16] * 3})
    weights = model(); weights['weights1'][0][0] = float('nan')
    with pytest.raises(ValueError):
        ExperimentalTeamPair(weights, {'home': [[0.] * 16] * 3, 'away': [[0.] * 16] * 3})
