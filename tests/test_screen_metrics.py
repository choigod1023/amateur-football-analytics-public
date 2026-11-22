from app.screen_metrics import clip_metrics, frame_metrics


def box(x, y, height=100):
    return [x, y - height, x + 40, y]


def test_distances_are_in_player_heights_and_need_two_players_for_spread():
    out = frame_metrics({'A': [box(100, 500), box(300, 500)], 'B': [box(200, 500)]}, 1000)
    assert out['players'] == {'A': 2, 'B': 1}
    assert out['A']['spread'] == 1.0                     # feet 200 px apart: 100 px from their centre, box height 100
    assert out['B']['spread'] is None
    assert out['A']['nearest_opponent'] == 1.0 and out['B']['nearest_opponent'] == 1.0
    assert out['A']['centre_x'] == 0.22


def test_scaling_the_picture_does_not_change_the_relative_values():
    small = frame_metrics({'A': [box(100, 500, 50), box(150, 500, 50)], 'B': [box(125, 540, 50)]}, 500)
    large = frame_metrics({'A': [box(200, 1000, 100), box(300, 1000, 100)], 'B': [box(250, 1080, 100)]}, 1000)
    assert small['A']['spread'] == large['A']['spread'] and small['B']['nearest_opponent'] == large['B']['nearest_opponent']


def test_near_ball_counts_only_players_within_three_heights_and_a_missing_ball_gives_none():
    boxes = {'A': [box(100, 500), box(900, 500)], 'B': []}
    assert frame_metrics(boxes, 1000, ball=(120, 500))['A']['near_ball'] == 1
    assert frame_metrics(boxes, 1000)['A']['near_ball'] is None
    assert frame_metrics(boxes, 1000)['B'] == {'centre_x': None, 'spread': None, 'nearest_opponent': None, 'near_ball': None}


def test_clip_metrics_skip_unknown_and_spectator_labels():
    tracks = {1: [{'frame': 0, 'team': 'A', 'box': box(100, 500)}, {'frame': 1, 'team': 'A', 'box': box(110, 500)}],
              2: [{'frame': 0, 'team': None, 'box': box(200, 500)}], 3: [{'frame': 0, 'team': 'S', 'box': box(300, 500)}]}
    out = clip_metrics(tracks, 2, 1000)
    assert out[0]['players'] == {'A': 1, 'B': 0} and out[1]['players'] == {'A': 1, 'B': 0}
