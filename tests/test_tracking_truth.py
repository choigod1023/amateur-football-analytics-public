from copy import deepcopy
from app.track_stitch import stitch_tracks
from scripts.audit_tracking_truth import pair_agreement


def row(frame):
    return {'frame': frame, 'team': 'A', 'box': [0, 0, 10, 30]}


def test_consumed_overlap_piece_still_has_membership_and_counts_in_evaluation():
    tracks = {'a': [row(0), row(1), row(2)], 'b': [row(2)]}
    original = deepcopy(tracks)
    membership = {}
    output, joins = stitch_tracks(tracks, 8, 3, membership=membership)
    assert joins == 1 and len(output['a']) == 3
    assert membership == {'a': 'a', 'b': 'a'}
    report = pair_agreement({'different': [['a', 'b'], ['a', 'missing']]}, membership)
    assert report['different']['total'] == 2
    assert report['different']['joined'] == 1 and report['different']['unresolved'] == 1
    assert tracks == original


def test_membership_tracks_whole_chain_and_does_not_include_empty_sources():
    tracks = {'a': [row(0)], 'b': [row(2)], 'c': [row(4)], 'empty': []}
    membership = {}
    output, joins = stitch_tracks(tracks, membership=membership)
    assert joins == 2 and membership == {'a': 'a', 'b': 'a', 'c': 'a'}
    assert len(output['a']) == 3


def test_nearby_raw_candidates_remain_candidates_not_identity_assignments():
    from scripts.audit_run_gap import nearby
    rows = nearby([0, 0, 10, 20], [{'id': 'x', 'box': [0, 0, 10, 20]}, {'id': 'y', 'box': [100, 0, 110, 20]}])
    assert rows == [{'id': 'x', 'box': [0, 0, 10, 20], 'distance_body_heights': 0.0}]
def test_reused_membership_cannot_keep_old_tracks():
    from app.track_stitch import stitch_tracks
    membership = {'old': 'old'}
    stitch_tracks({}, membership=membership)
    assert membership == {}
