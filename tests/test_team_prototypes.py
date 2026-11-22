import numpy as np
from scripts.research_team_prototypes import classify


def test_prototypes_allow_unknown_and_reject_far_and_ambiguous_features():
    zeros = np.zeros((1, 16)); ones = np.ones((1, 16))
    assert classify(None, [zeros, ones], .4) is None
    assert classify(zeros[0], [zeros, np.empty((0, 16))], .4) is None
    assert classify(np.full(16, .5), [zeros, ones], 3.) is None
    assert classify(np.full(16, .2), [zeros, ones], .4) is None
    assert classify(np.full(16, .02), [zeros, ones], .4) == 0
    assert classify(np.full(16, .98), [zeros, ones], .4) == 1
