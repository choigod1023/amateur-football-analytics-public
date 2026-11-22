from app.track_vote import SPECTATOR, TRACKER_SETTINGS, drop_short_tracks, is_person_track, majority_label, summarise_tracks, vote_tracks


def test_majority_label_ignores_spectator_frames_and_refuses_ties():
    assert majority_label(['A', 'A', 'B', SPECTATOR, SPECTATOR]) == 'A'
    assert majority_label(['A', 'B']) is None
    assert majority_label([SPECTATOR, SPECTATOR]) is None
    assert majority_label([]) is None


def test_person_track_needs_half_of_its_frames_outside_the_stands():
    assert is_person_track(['A', 'B', SPECTATOR])
    assert not is_person_track(['A', SPECTATOR, SPECTATOR])
    assert not is_person_track([])


def test_vote_fixes_flickering_colour_and_keeps_spectators():
    tracks = {1: [(0, 'A'), (1, 'B'), (2, 'A'), (3, 'A')], 2: [(0, SPECTATOR), (1, SPECTATOR)], 3: [(0, 'A'), (1, 'B')]}
    voted = vote_tracks(tracks)
    assert [label for _, label in voted[1]] == ['A'] * 4
    assert [label for _, label in voted[2]] == [SPECTATOR] * 2
    assert [label for _, label in voted[3]] == [None, None]          # a tie stays unknown, no guess
    assert [frame for frame, _ in voted[1]] == [0, 1, 2, 3]


def test_summary_counts_fragmentation_and_colour_changes():
    tracks = {1: [(i, 'A') for i in range(30)], 2: [(0, 'A'), (1, 'B'), (2, 'B')], 3: [(0, SPECTATOR)] * 5}
    summary = summarise_tracks(tracks, clip_frames=50)
    assert summary['person_tracks'] == 2 and summary['long_tracks'] == 1
    assert summary['tracks_with_colour_change'] == 1 and summary['median_length'] == 30
    assert summary['mean_colour_agreement'] == round((1 + 2 / 3) / 2, 3)
    assert summarise_tracks({}, 50)['mean_colour_agreement'] is None
    assert set(TRACKER_SETTINGS) == {'track_buffer', 'match_thresh', 'track_high_thresh', 'track_low_thresh'}


def test_short_tracks_are_dropped_and_the_rest_keep_their_rows():
    tracks = {1: [(i, 'A') for i in range(12)], 2: [(0, 'B'), (1, 'B')], 3: []}
    kept = drop_short_tracks(tracks, 10)
    assert list(kept) == [1] and kept[1] == tracks[1]
    assert drop_short_tracks(tracks, 1).keys() == {1, 2}            # an empty track has no rows and never counts
