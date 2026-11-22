import numpy as np
from scripts.evaluate_team_feature_smoothing_detected import smoothed_predictions


class Classifier:
    def _classify(self, feature):
        return None if feature is None else float(feature[0])


def test_missing_crop_never_reuses_history_and_gap_resets():
    h = {name: {} for name in ('ema3', 'ema7', 'window3')}
    fn = lambda f, n: smoothed_predictions(Classifier(), f, 'track', n, h)
    fn(np.array([1.]), 0)
    assert all(x is None for x in fn(None, 1).values())
    assert all(x == 0 for x in fn(np.array([0.]), 5).values())


def test_history_is_track_scoped():
    h = {name: {} for name in ('ema3', 'ema7', 'window3')}
    smoothed_predictions(Classifier(), np.array([1.]), 'one', 0, h)
    out = smoothed_predictions(Classifier(), np.array([0.]), 'two', 1, h)
    assert all(x == 0 for x in out.values())
