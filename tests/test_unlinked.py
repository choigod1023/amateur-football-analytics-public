from app.track_stitch import stitch_tracks, _observed_endpoint


def row(f, x=10, height=30, **extra):
    return dict(frame=f, team='B', box=[x, 100-height, x+10, 100], **extra)


def test_collapsed_terminal_detection_does_not_destroy_connection():
    a = [row(i) for i in range(8)] + [row(8, x=-10, height=10), row(9, x=-20, height=7)]
    b = [row(i) for i in range(10, 15)]
    assert len(_observed_endpoint(a)) == 8
    assert stitch_tracks({'a': a, 'b': b}, 8, require_mutual=True)[1] == 0
    assert stitch_tracks({'a': a, 'b': b}, 8, require_mutual=True, endpoint_evidence=True)[1] == 1


def test_observed_nonoverlapping_boxes_in_same_frame_are_not_backfill():
    a = [row(i) for i in range(5)]
    b = [row(i, x=28) for i in range(4, 10)]
    assert stitch_tracks({'a': a, 'b': b}, 8, 3)[1] == 1
    assert stitch_tracks({'a': a, 'b': b}, 8, 3, endpoint_evidence=True)[1] == 0


def test_evidence_matching_does_not_modify_input_rows():
    import copy
    tracks = {'a': [row(i) for i in range(8)] + [row(8, interpolated=True)], 'b': [row(i) for i in range(9, 15)]}
    before = copy.deepcopy(tracks)
    stitch_tracks(tracks, 8, 3, endpoint_evidence=True)
    assert before == tracks
