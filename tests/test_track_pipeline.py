import numpy as np

from app.track_pipeline import enforce_team_size, finalize_tracks

CLASSES = ['referee', 'spectator', 'team_a', 'team_b']
A = [0.0, 0.0, 0.9, 0.1]
B = [0.0, 0.0, 0.1, 0.9]
SPECTATOR = [0.0, 0.95, 0.03, 0.02]


def rows(first, last, x):
    return [(f, [x + f, 500, x + f + 30, 580]) for f in range(first, last + 1)]


def test_tracks_get_a_label_short_ones_are_dropped_and_gaps_are_filled_and_marked():
    tracks = {1: rows(0, 11, 100) + rows(14, 25, 100), 2: rows(0, 3, 600), 3: rows(0, 25, 900), 4: rows(0, 25, 1500)}
    scores = {1: [A] * 24, 2: [B] * 4, 3: [B] * 26, 4: [SPECTATOR] * 26}
    neon = {1: [0.2] * 24, 2: [0.0] * 4, 3: [0.0] * 26, 4: [0.0] * 26}
    result = finalize_tracks(tracks, scores, neon, CLASSES, 26, min_track_length=10, fill_gap_frames=8)
    kept = result['tracks']
    assert set(kept) == {1, 3, 4}                                            # the 4-frame track is gone, the spectator track stays untouched
    assert {r['team'] for r in kept[1]} == {'A'} and {r['team'] for r in kept[3]} == {'B'} and {r['team'] for r in kept[4]} == {'S'}
    assert [r['frame'] for r in kept[1]] == list(range(26)) and result['interpolated_rows'] == 2
    assert [r['frame'] for r in kept[1] if r.get('interpolated')] == [12, 13]
    assert result['summary']['person_tracks'] == 2


def test_a_window_label_follows_a_track_that_switches_from_one_team_to_the_other():
    tracks = {7: rows(0, 23, 100)}
    scores = {7: [A] * 12 + [B] * 12}
    result = finalize_tracks(tracks, scores, {7: [0.0] * 24}, CLASSES, 24, label_window=3)
    labels = [r['team'] for r in result['tracks'][7]]
    assert labels[0] == 'A' and labels[-1] == 'B'
    whole = finalize_tracks(tracks, scores, {7: [0.0] * 24}, CLASSES, 24)
    assert {r['team'] for r in whole['tracks'][7]} == {None}                 # one label for the whole track cannot decide


def test_a_team_can_never_show_more_players_than_its_size_in_one_frame():
    strong = [0.0, 0.0, 0.9, 0.1]
    weak_b_leaning = [0.0, 0.0, 0.45, 0.4]            # labelled A, but only just
    rows_by_id = {1: [{'frame': 0, 'team': 'A', 'box': [0, 0, 1, 1]}], 2: [{'frame': 0, 'team': 'A', 'box': [0, 0, 1, 1]}], 3: [{'frame': 0, 'team': 'A', 'box': [0, 0, 1, 1]}]}
    scores = {1: [strong], 2: [strong], 3: [weak_b_leaning]}
    changed = enforce_team_size(rows_by_id, scores, CLASSES, team_size=2)
    assert changed == 1 and rows_by_id[3][0]['team'] == 'B' and rows_by_id[1][0]['team'] == 'A'


def test_a_surplus_box_with_no_chance_of_being_the_other_team_is_left_unlabelled():
    strong = [0.0, 0.0, 0.95, 0.02]
    rows_by_id = {t: [{'frame': 0, 'team': 'A', 'box': [0, 0, 1, 1]}] for t in (1, 2, 3)}
    scores = {1: [strong], 2: [strong], 3: [[0.0, 0.0, 0.9, 0.05]]}
    enforce_team_size(rows_by_id, scores, CLASSES, team_size=2)
    assert [rows_by_id[t][0]['team'] for t in (1, 2, 3)].count(None) == 1
    assert [rows_by_id[t][0]['team'] for t in (1, 2, 3)].count('A') == 2


def test_backfill_adds_the_birth_detection_the_tracker_did_not_report():
    from app.track_pipeline import backfill_births
    tracks = {1: [(5, [10.0, 10.0, 20.0, 40.0]), (6, [11.0, 10.0, 21.0, 40.0])]}
    scores = {1: [[0.1, 0.2, 0.6, 0.1], [0.1, 0.2, 0.6, 0.1]]}
    neon = {1: [0.0, 0.0]}
    detections = {4: [([9.0, 10.0, 19.0, 40.0], 'f4'), ([200.0, 10.0, 210.0, 40.0], 'far')], 3: [([8.0, 10.0, 18.0, 40.0], 'f3')]}
    added = backfill_births(tracks, scores, neon, detections, lambda rows: [[0.0, 0.0, 1.0, 0.0] for _ in rows], lambda row: 0.5, max_frames=1)
    assert added == 1 and [f for f, _ in tracks[1]] == [4, 5, 6] and neon[1][0] == 0.5 and len(scores[1]) == 3
    assert backfill_births(tracks, scores, neon, detections, lambda rows: [[0.0, 0.0, 1.0, 0.0]] * len(rows), lambda row: 0.0, max_frames=3) == 1   # frame 3 is added, frame 2 has nothing
    assert [f for f, _ in tracks[1]][:2] == [3, 4]


def test_backfill_leaves_a_detection_that_another_track_already_uses():
    from app.track_pipeline import backfill_births
    tracks = {1: [(5, [10.0, 10.0, 20.0, 40.0])], 2: [(4, [9.0, 10.0, 19.0, 40.0])]}
    scores = {1: [[0.0, 0.0, 1.0, 0.0]], 2: [[0.0, 0.0, 1.0, 0.0]]}
    neon = {1: [0.0], 2: [0.0]}
    detections = {4: [([9.0, 10.0, 19.0, 40.0], 'f4')]}
    assert backfill_births(tracks, scores, neon, detections, lambda rows: [[0.0, 0.0, 1.0, 0.0]] * len(rows), lambda row: 0.0) == 0
