"""Relative team measures computed in image space, without a pitch calibration.

Every distance is divided by the height of the player's box, so it is a unitless "player heights" value. Perspective
makes far players look smaller and the same pitch distance look shorter, so these numbers describe how the picture
looks and must not be read as metres, speeds or real distances. A team with fewer than two labelled players in a
frame gets None for the measures that need two or more.
"""
import math


def _feet(box):
    return ((box[0] + box[2]) / 2, box[3])


def _height(box):
    return max(1.0, box[3] - box[1])


def _distance(first, second):
    scale = (_height(first) + _height(second)) / 2
    (x1, y1), (x2, y2) = _feet(first), _feet(second)
    return math.hypot(x1 - x2, y1 - y2) / scale


def frame_metrics(boxes_by_team, width, ball=None):
    """boxes_by_team: {'A': [box, ...], 'B': [box, ...]} with boxes [x1, y1, x2, y2] in pixels.

    ball: optional (x, y) in pixels. Returns counts, centre, spread, the typical gap to the nearest opponent and the
    number of players within three player heights of the ball, per team.
    """
    result = {'players': {team: len(boxes) for team, boxes in boxes_by_team.items()}}
    for team, boxes in boxes_by_team.items():
        other = [box for name, group in boxes_by_team.items() if name != team for box in group]
        if boxes:
            centre = sum(_feet(box)[0] for box in boxes) / len(boxes) / width
        else:
            centre = None
        spread = None
        if len(boxes) >= 2:
            mean_height = sum(_height(box) for box in boxes) / len(boxes)
            xs, ys = [_feet(box)[0] for box in boxes], [_feet(box)[1] for box in boxes]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            spread = round(math.sqrt(sum((x - mx) ** 2 + (y - my) ** 2 for x, y in zip(xs, ys)) / len(xs)) / mean_height, 2)
        gaps = [min(_distance(box, o) for o in other) for box in boxes] if boxes and other else []
        near = None
        if ball is not None:
            near = sum(1 for box in boxes if math.hypot(_feet(box)[0] - ball[0], _feet(box)[1] - ball[1]) / _height(box) <= 3.0)
        result[team] = {'centre_x': None if centre is None else round(centre, 3), 'spread': spread,
                        'nearest_opponent': round(sum(gaps) / len(gaps), 2) if gaps else None, 'near_ball': near}
    return result


def clip_metrics(tracks, frame_count, width, balls=None, teams=('A', 'B')):
    """tracks: {id: [{'frame', 'team', 'box'}]}; balls: {frame: (x, y)}. Returns one entry per frame."""
    per_frame = [{team: [] for team in teams} for _ in range(frame_count)]
    for rows in tracks.values():
        for row in rows:
            if row['team'] in teams and 0 <= row['frame'] < frame_count:
                per_frame[row['frame']][row['team']].append(row['box'])
    return [frame_metrics(per_frame[i], width, (balls or {}).get(i)) for i in range(frame_count)]
