import numpy as np
import pytest
import torch
from scripts import run_live_feedback_identity as live


FRAME = np.zeros((100, 100, 3), np.uint8)
TRACKS = np.array([[10, 10, 20, 50, 1], [30, 10, 40, 50, 2],
                   [50, 10, 60, 50, 3], [70, 10, 80, 50, 4]], np.float32)


def encoded_features(frame, box):
    features = np.zeros(len(live.FEATURE_NAMES), np.float32)
    features[min(3, max(0, round((box[0] * 100 - 10) / 20)))] = 1.
    return features


def tiny_cpu_model():
    net = torch.nn.Linear(len(live.FEATURE_NAMES), 4)
    with torch.no_grad():
        net.weight.zero_(); net.bias.zero_()
        for i in range(4):
            net.weight[i, i] = 4.
    net.eval()
    return {'nets': [net], 'mean': np.zeros(len(live.FEATURE_NAMES), np.float32),
            'spread': np.ones(len(live.FEATURE_NAMES), np.float32),
            'classes': ['team_a', 'team_b', 'referee', 'not_a_role']}


def test_real_cpu_model_preserves_counts_labels_and_ignores_unknown(monkeypatch):
    monkeypatch.setattr(live, 'box_features', encoded_features)
    monkeypatch.setattr(live, 'load_model', lambda _: tiny_cpu_model())
    individual, batched = live.TeamVotes('test'), live.TeamVotes('test')
    for _ in range(3):
        for row in TRACKS:
            individual.observe(int(row[4]), FRAME, row[:4])
        batched.observe_many(FRAME, TRACKS)
        assert individual.votes == batched.votes
        assert [individual.label(i) for i in range(1, 5)] == [batched.label(i) for i in range(1, 5)]
    assert [batched.label(i) for i in range(1, 5)] == ['A', 'B', None, None]
    assert 4 not in batched.votes


def test_batch_calls_model_once_and_empty_calls_neither_model_nor_features(monkeypatch):
    calls = []
    monkeypatch.setattr(live, 'box_features', encoded_features)
    def fake_predict(model, features):
        calls.append(len(features))
        return np.tile([.9, .1], (len(features), 1))
    monkeypatch.setattr(live, 'predict', fake_predict)
    voting = live.TeamVotes(); voting.model = {'classes': ['team_a', 'team_b']}
    voting.observe_many(FRAME, TRACKS)
    assert calls == [4]
    monkeypatch.setattr(live, 'box_features', lambda *_: pytest.fail('Empty input must not extract features'))
    voting.observe_many(FRAME, np.empty((0, 8)))
    assert calls == [4]


def test_colour_heuristic_and_counter_tie_order_match(monkeypatch):
    def features(frame, box):
        result = np.zeros(len(live.FEATURE_NAMES), np.float32)
        if box[0] < .2:
            result[live.FEATURE_NAMES.index('neon')] = .15
        elif box[0] < .4:
            result[live.FEATURE_NAMES.index('dark')] = .4
        return result
    monkeypatch.setattr(live, 'box_features', features)
    individual, batched = live.TeamVotes(minimum=1), live.TeamVotes(minimum=1)
    for x in (10, 30, 50, 30, 10):
        row = np.array([[x, 10, x+10, 50, 11]], np.float32)
        individual.observe(11, FRAME, row[0, :4]); batched.observe_many(FRAME, row)
        assert individual.votes == batched.votes
        assert individual.label(11) == batched.label(11)


def test_model_result_count_mismatch_cannot_drop_people(monkeypatch):
    monkeypatch.setattr(live, 'box_features', encoded_features)
    monkeypatch.setattr(live, 'predict', lambda *_: np.empty((0, 2)))
    voting = live.TeamVotes(); voting.model = {'classes': ['team_a', 'team_b']}
    with pytest.raises(ValueError, match='number of person results'):
        voting.observe_many(FRAME, TRACKS)
    assert voting.votes == {}
