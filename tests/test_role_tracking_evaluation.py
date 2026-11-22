import json
from app.difference_review import fingerprint
from scripts.evaluate_role_tracking import summarize, reviewed_pairs


def frame(t, team='A', visible=True):
    return {'time': t, 'source_tracks': [[0, 0, 10, 20, 1]],
            'track_outcomes': [{'id': '1', 'team': team, 'projection_status': 'projected',
                                'position_status': 'retained', 'point_m': [0, 0]}],
            'display_players': [{'id': '1', 'team': 'away', 'x': .5, 'y': .5}] if visible else [],
            'players': [], 'position_rejected': 0, 'alerts': []}


def test_continuity_counts_do_not_become_accuracy():
    result = summarize([frame(0), frame(.2, 'B', False)])
    assert result['team_flips'] == 1
    assert result['disappeared_from_map_while_still_tracked'] == 1
    assert result['identity_accuracy'] is result['position_error_m'] is None


def test_time_gap_does_not_count_as_adjacent_observation():
    result = summarize([frame(0), frame(2, 'B', False)])
    assert result.get('team_flips', 0) == 0
    assert result.get('disappeared_from_map_while_still_tracked', 0) == 0


def test_review_requires_current_human_fingerprint_and_endpoint_geometry(tmp_path):
    directory = tmp_path/'differences'; (directory/'answers').mkdir(parents=True)
    item = {'id': 'd0108', 'kind': 'tracking', 'source_sha256': 'sha', 'boundary': {
        'end': 0, 'start': .2, 'before_box': [0, 0, 10, 20], 'after_box': [0, 0, 10, 20]}}
    (directory/'queue.json').write_text(json.dumps({'items': [item]}))
    answer = {'id': 'd0108', 'source': 'human', 'fingerprint': fingerprint(item), 'verdict': 'same'}
    path = directory/'answers/d0108.json'; path.write_text(json.dumps(answer))
    rows = [{'time': 0, 'observed_tracks': [[0, 0, 10, 20, 4]]},
            {'time': .2, 'observed_tracks': [[0, 0, 10, 20, 9]]}]
    result = reviewed_pairs(rows, tmp_path, 'sha')
    assert result[0]['prediction'] == 'different' and result[0]['correct'] is False
    rows[1]['observed_tracks'] = [[100, 100, 110, 120, 9]]
    assert reviewed_pairs(rows, tmp_path, 'sha')[0]['correct'] is None
    answer['fingerprint'] = 'stale'; path.write_text(json.dumps(answer))
    assert reviewed_pairs(rows, tmp_path, 'sha') == []
