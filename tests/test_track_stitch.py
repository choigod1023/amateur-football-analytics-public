from app.track_stitch import drop_duplicates, fill_gaps, stitch_tracks


def row(frame, x, team='A', height=80):
    return {'frame': frame, 'team': team, 'box': [x, 500, x + 30, 500 + height]}


def test_a_nearby_continuation_after_a_short_gap_is_joined():
    tracks = {1: [row(0, 100), row(1, 110), row(2, 120)], 2: [row(4, 140), row(5, 150)]}
    joined, count = stitch_tracks(tracks)
    assert count == 1 and list(joined) == [1]
    assert [r['frame'] for r in joined[1]] == [0, 1, 2, 4, 5]


def test_contradicting_teams_far_jumps_and_long_gaps_are_not_joined():
    assert stitch_tracks({1: [row(0, 100), row(1, 110)], 2: [row(3, 130, 'B')]})[1] == 0
    assert stitch_tracks({1: [row(0, 100), row(1, 110)], 2: [row(3, 900)]})[1] == 0
    assert stitch_tracks({1: [row(0, 100), row(1, 110)], 2: [row(20, 130)]})[1] == 0


def test_unknown_team_does_not_block_and_overlapping_tracks_are_never_joined():
    assert stitch_tracks({1: [row(0, 100), row(1, 110)], 2: [row(3, 130, None)]})[1] == 1
    assert stitch_tracks({1: [row(0, 100), row(1, 110), row(2, 120)], 2: [row(1, 112), row(2, 122)]})[1] == 0


def test_each_piece_joins_once_and_chains_keep_the_first_id():
    tracks = {5: [row(0, 100), row(1, 110)], 6: [row(3, 130)], 7: [row(5, 150), row(6, 160)], 8: [row(3, 135)]}
    joined, count = stitch_tracks(tracks)
    assert count == 2 and 5 in joined and 6 not in joined and 7 not in joined
    assert sum(len(v) for v in joined.values()) == sum(len(v) for v in tracks.values())


def test_a_short_gap_is_filled_by_interpolation_and_marked():
    tracks = {1: [row(0, 100), row(1, 110), row(4, 140), row(5, 150)]}
    filled, added = fill_gaps(tracks)
    assert added == 2
    assert [r['frame'] for r in filled[1]] == [0, 1, 2, 3, 4, 5]
    middle = [r for r in filled[1] if r.get('interpolated')]
    assert [r['frame'] for r in middle] == [2, 3] and middle[0]['box'][0] == 120.0 and middle[1]['box'][0] == 130.0
    assert all('interpolated' not in r for r in filled[1] if r['frame'] not in (2, 3))


def test_a_long_gap_is_left_alone_and_the_input_is_not_changed():
    tracks = {1: [row(0, 100), row(20, 300)]}
    filled, added = fill_gaps(tracks, max_gap=8)
    assert added == 0 and len(filled[1]) == 2
    assert len(tracks[1]) == 2 and 'interpolated' not in tracks[1][0]


def test_the_shorter_of_two_tracks_on_the_same_person_loses_the_overlapping_rows():
    long_track = [row(i, 100 + i) for i in range(10)]
    twin = [row(i, 102 + i, team='B') for i in range(3, 6)]                 # a second track on the same person for 3 frames
    kept, dropped = drop_duplicates({1: long_track, 2: twin})
    assert dropped == 3 and 2 not in kept and len(kept[1]) == 10


def test_two_players_standing_apart_are_both_kept_and_partial_overlap_does_not_count():
    apart = {1: [row(i, 100) for i in range(5)], 2: [row(i, 160) for i in range(5)]}
    assert drop_duplicates(apart)[1] == 0
    near = {1: [row(i, 100) for i in range(5)], 2: [row(i, 125) for i in range(5)]}      # 25 px apart on 80 px tall boxes
    assert drop_duplicates(near)[1] == 0


def test_the_conflict_is_resolved_per_frame_so_a_track_keeps_its_other_frames():
    first = [row(i, 100) for i in range(6)]
    second = [row(2, 101), row(8, 400), row(9, 410)]
    kept, dropped = drop_duplicates({1: first, 2: second})
    assert dropped == 1 and [r['frame'] for r in kept[2]] == [8, 9]


def test_a_long_gap_is_joined_and_filled_but_not_where_another_track_already_shows_the_person():
    def row(frame, x, team='B'):
        return {'frame': frame, 'team': team, 'box': [x, 100.0, x + 20.0, 160.0]}
    first = [row(f, 100.0 + f) for f in range(0, 10)]
    second = [row(f, 100.0 + f) for f in range(30, 40)]                         # 20 frames later, still on the straight line
    joined, joins = stitch_tracks({1: first, 2: second}, max_gap=25)
    assert joins == 1 and len(joined) == 1
    assert stitch_tracks({1: first, 2: second}, max_gap=8)[1] == 0              # the old limit would leave two pieces
    filled, added = fill_gaps(joined, max_gap=25)
    assert added == 20 and [r['frame'] for r in filled[1]] == list(range(0, 40))
    twin = [row(f, 100.0 + f) for f in range(10, 30)]                             # another track shows him in the gap
    blocked, added = fill_gaps({1: first + second, 3: twin}, max_gap=25, avoid_covered=True)
    assert added == 0


def test_the_team_size_is_checked_again_after_filling():
    from app.track_pipeline import cap_team_rows
    rows = {i: [{'frame': 0, 'team': 'B', 'box': [i * 50.0, 0.0, i * 50.0 + 20, 60.0], **({'interpolated': True} if i >= 11 else {})}] for i in range(13)}
    kept, dropped = cap_team_rows(rows, 11)
    assert dropped == 2 and all(i < 11 for i in kept)                              # the two added rows go first


def test_a_small_overlap_is_joined_only_when_allowed_and_the_double_frames_are_dropped():
    tracks = {1: [row(0, 100), row(1, 110), row(2, 120), row(3, 130)], 2: [row(2, 122), row(3, 132), row(4, 140)]}      # the second piece starts two frames early (an added back birth)
    assert stitch_tracks(tracks)[1] == 0
    joined, count = stitch_tracks(tracks, max_overlap=3)
    assert count == 1 and [r['frame'] for r in joined[1]] == [0, 1, 2, 3, 4]
    far = {1: [row(0, 100), row(1, 110)], 2: [row(0, 800), row(1, 810), row(2, 820)]}
    assert stitch_tracks(far, max_overlap=3)[1] == 0
