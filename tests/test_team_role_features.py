import numpy as np

from app.team_role_features import CLASSES, FEATURE_NAMES, box_features, class_of


def scene(colour_bgr):
    image = np.full((200, 400, 3), (40, 90, 40), np.uint8)          # green pitch
    image[60:180, 100:160] = colour_bgr
    return image


def test_labels_map_to_four_classes_and_unusable_labels_are_dropped():
    assert class_of('referee', 'unknown') == 'referee' and class_of('spectator', 'unknown') == 'spectator'
    assert class_of('goalkeeper', 'team_b') == 'team_b' and class_of('player', 'team_a') == 'team_a'
    assert class_of('duplicate', 'unknown') is None and class_of('player', 'unknown') is None
    assert set(CLASSES) == {'referee', 'spectator', 'team_a', 'team_b'}


def test_neon_vest_and_dark_shirt_give_different_features():
    box = [100 / 400, 60 / 200, 160 / 400, 180 / 200]
    names = list(FEATURE_NAMES)
    neon = box_features(scene((40, 255, 200)), box)                    # yellow-green in BGR
    dark = box_features(scene((20, 20, 20)), box)
    assert len(neon) == len(FEATURE_NAMES) and neon.dtype == np.float32
    assert neon[names.index('neon')] > 0.9 and dark[names.index('neon')] == 0
    assert dark[names.index('dark')] > 0.9 and neon[names.index('dark')] == 0


def test_an_empty_or_outside_box_gives_zeros_instead_of_an_error():
    assert not box_features(scene((0, 0, 0)), [1.2, 1.2, 1.4, 1.4]).any()
