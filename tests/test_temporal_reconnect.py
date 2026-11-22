import json
import numpy as np
import pytest
from app.learned_reconnect import descriptor
from app.temporal_reconnect import TEMPORAL_FEATURES, TemporalLinker, sequence_features, fit_temporal, temporal_score


FRAME = np.zeros((200, 300, 3), np.uint8)


def seq(times, xs):
    return [{'time': t, 'box': [x, 20, x + 20, 80],
             'descriptor': descriptor(FRAME, [x, 20, x + 20, 80])} for t, x in zip(times, xs)]


def model(bias=10):
    return {'features': TEMPORAL_FEATURES, 'mean': [0.] * 14, 'scale': [1.] * 14,
            'weights': [0.] * 14, 'bias': bias, 'threshold': .9,
            'ambiguity_margin': .15, 'max_prediction_residual_heights': 1.5}


def row(x, identity):
    return [x, 20, x + 20, 80, identity]


def test_same_color_opposite_motion_has_different_temporal_features():
    before = seq([0, .2, .4], [20, 22, 24])
    same = sequence_features(before, seq([.8, 1., 1.2], [28, 30, 32]))
    opposite = sequence_features(before, seq([.8, 1., 1.2], [28, 26, 24]))
    assert np.allclose(same[:6], opposite[:6])  # identical uniform
    assert same[9] == pytest.approx(0.)
    assert same[10] == pytest.approx(0.)
    assert opposite[11] > same[11]
    assert opposite[12] > same[12]
    assert sequence_features(before[:2], before) is None


def test_training_uses_motion_without_identity_and_is_reproducible():
    before = seq([0, .2, .4], [20, 22, 24])
    yes = sequence_features(before, seq([.8, 1., 1.2], [28, 30, 32]))
    no = sequence_features(before, seq([.8, 1., 1.2], [28, 26, 24]))
    x = np.array([yes, yes, no, no]); y = [1, 1, 0, 0]
    trained = fit_temporal(x, y)
    assert trained == fit_temporal(x, y)
    assert temporal_score(trained, yes) > temporal_score(trained, no)
    assert trained['features'] == TEMPORAL_FEATURES


def test_confirmation_requires_three_observations_and_does_not_make_boxes():
    linker = TemporalLinker(model())
    for t, x in [(0, 20), (.2, 22), (.4, 24)]:
        linker.update(t, FRAME, [row(x, 1)])
    assert linker.update(.6, FRAME, [])[0] == {}
    assert linker.update(.8, FRAME, [row(28, 2)])[1] == []
    assert linker.update(1., FRAME, [row(30, 2)])[1] == []
    mapping, events = linker.update(1.2, FRAME, [row(32, 2)])
    assert mapping == {'2': '1'}
    assert events[0]['birth_time'] == .8
    json.dumps(events)


def test_nonconsecutive_birth_is_not_relabelled_after_publication():
    linker = TemporalLinker(model())
    for t in (0, .2, .4):
        linker.update(t, FRAME, [row(20, 1)])
    for t in (.8, 1.2, 1.4, 1.6):
        mapping, events = linker.update(t, FRAME, [row(20, 2)])
        assert mapping == {'2': '2'} and not events


def test_overlapping_track_histories_and_ambiguity_abstain():
    linker = TemporalLinker(model())
    for t in (0, .2, .4):
        linker.update(t, FRAME, [row(20, 1), row(22, 3)])
    for t in (.8, 1., 1.2):
        mapping, events = linker.update(t, FRAME, [row(21, 2)])
    assert mapping == {'2': '2'} and not events
    linker = TemporalLinker(model())
    for t in (0, .2, .4):
        linker.update(t, FRAME, [row(20, 1)])
    linker.update(.6, FRAME, [row(20, 1), row(20, 2)])
    linker.update(.8, FRAME, [row(20, 2)])
    assert linker.update(1., FRAME, [row(20, 2)])[0] == {'2': '2'}


def test_motion_gate_and_simultaneous_alias_return():
    linker = TemporalLinker(model())
    for t in (0, .2, .4):
        linker.update(t, FRAME, [row(20, 1)])
    for t in (.8, 1., 1.2):
        mapping, events = linker.update(t, FRAME, [row(200, 2)])
    assert mapping == {'2': '2'} and not events
    linker = TemporalLinker(model())
    for t in (0, .2, .4):
        linker.update(t, FRAME, [row(20, 1)])
    for t in (.8, 1., 1.2):
        linker.update(t, FRAME, [row(20, 2)])
    mapping, _ = linker.update(1.4, FRAME, [row(20, 1), row(22, 2)])
    assert len(set(mapping.values())) == 2
