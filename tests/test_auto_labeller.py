import numpy as np

from app import auto_labeller as al


def test_time_groups_keep_close_times_together():
    groups = al.time_groups([10, 50, 119, 121, 300])
    assert groups[0] == groups[1] == groups[2]
    assert groups[3] != groups[2]


def test_group_folds_never_split_a_group():
    groups = [0, 0, 0, 1, 1, 2, 3, 3, 3, 3, 4, 5]
    folds = al.group_folds(groups, 3)
    for g in set(groups):
        assert len({f for f, gg in zip(folds, groups) if gg == g}) == 1
    assert set(folds) == {0, 1, 2}


def test_near_any():
    assert al.near_any(100.0, [110.0])
    assert not al.near_any(100.0, [120.0])


def test_ridge_learns_a_separable_problem():
    rng = np.random.RandomState(0)
    x = np.vstack([rng.randn(40, 3) + 2, rng.randn(40, 3) - 2])
    y = np.array([1] * 40 + [0] * 40)
    model = al.Ridge(1.0).fit(x, y)
    p = model.predict(x)
    assert ((p > 0.5) == (y == 1)).mean() > 0.95
    again = al.Ridge.from_json(model.to_json()).predict(x)
    assert np.allclose(p, again)


def test_pick_thresholds_leaves_a_level_empty_when_the_target_is_missed():
    prob = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05] * 2
    label = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0] * 2            # no probability separates the labels
    hi, lo = al.pick_thresholds(prob, label)
    assert hi is None and lo is None


def test_pick_thresholds_finds_clean_levels():
    prob = [0.95] * 10 + [0.5] * 10 + [0.05] * 10
    label = [1] * 10 + [1, 0] * 5 + [0] * 10
    hi, lo = al.pick_thresholds(prob, label)
    assert hi == 0.95 and lo == 0.05


def test_decide_three_levels():
    assert al.decide(0.99, 0.9, 0.2) == 'accept'
    assert al.decide(0.1, 0.9, 0.2) == 'reject'
    assert al.decide(0.5, 0.9, 0.2) == 'ask'
    assert al.decide(0.99, None, 0.2) == 'ask'


def test_scope_is_the_judged_band():
    assert al.in_scope(0.40, 'A') and al.in_scope(0.36, 'B')
    assert not al.in_scope(0.30, 'B') and not al.in_scope(0.55, 'A') and not al.in_scope(0.40, 'AB')


def test_box_features_separate_a_bright_figure_from_grass():
    import cv2
    image = np.full((200, 200, 3), (40, 120, 40), dtype=np.uint8)
    image[60:140, 90:110] = (30, 30, 30)
    person = al.box_features(cv2, image, [90, 60, 110, 140], 0.4, 'B')
    grass = al.box_features(cv2, image, [10, 60, 30, 140], 0.4, 'A')
    assert person['is_b'] == 1.0 and grass['is_b'] == 0.0
    assert person['ring_diff'] > grass['ring_diff']
    assert grass['green'] > person['green']
    assert set(al.BASE_FEATURES) <= set(person)


def test_wilson_lower_and_summarise():
    assert al.wilson_lower(0, 0) == 0.0
    assert 0.8 < al.wilson_lower(36, 36) < 0.95
    summary = al.summarise(['accept', 'accept', 'reject', 'ask'], [1, 0, 0, 1])
    assert summary == {'accept': 2, 'accept_people': 1, 'reject': 1, 'reject_nonpeople': 1, 'ask': 1, 'ask_people': 1}
