from app.track_stitch import stitch_tracks, _local_team


def rows(first, labels):
    return [{'frame': first+i, 'team': team, 'box': [100+i*.05, 10, 120+i*.05, 50]} for i, team in enumerate(labels)]


def test_local_endpoint_guard_blocks_mixed_track_cross_team_bridge():
    tracks = {'a': rows(0, ['B'] + ['A']*5), 'b': rows(6, ['B']*5 + ['A'])}
    _, prior = stitch_tracks(tracks, endpoint_evidence=True, require_mutual=True)
    kept, new = stitch_tracks(tracks, endpoint_evidence=True, require_mutual=True, endpoint_team_guard=True)
    assert prior == 1 and new == 0 and set(kept) == {'a', 'b'}


def test_endpoint_guard_keeps_matching_votes_and_original_rows():
    tracks = {'a': rows(0, ['B'] + ['A']*5), 'b': rows(6, ['A']*5 + ['B'])}
    kept, joins = stitch_tracks(tracks, endpoint_evidence=True, require_mutual=True, endpoint_team_guard=True)
    assert joins == 1 and len(kept['a']) == 12
    assert kept['a'][0] is tracks['a'][0]


def test_unknown_and_short_samples_do_not_become_confident_team():
    assert _local_team(rows(0, ['A', None, 'A', None, 'A'])) is None
    assert _local_team(rows(0, ['A', 'A'])) is None
    assert _local_team(rows(0, ['A']*4+[None])) == 'A'
