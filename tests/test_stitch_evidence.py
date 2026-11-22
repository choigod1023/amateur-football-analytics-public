from copy import deepcopy
from app.track_stitch import stitch_tracks


def rows(start, end, x=0):
    return [{'frame': f, 'team': 'B', 'box': [x + f, 0, x + f + 10, 30]} for f in range(start, end + 1)]


def test_human_different_constraint_applies_transitively_and_keeps_inputs():
    data = {'a': rows(0, 2), 'b': rows(4, 6), 'c': rows(8, 10)}
    before = deepcopy(data)
    output, joins = stitch_tracks(data, different_pairs=[('a', 'c')])
    assert joins == 1
    assert not any(any(r['frame'] == 0 for r in group) and any(r['frame'] == 10 for r in group) for group in output.values())
    assert data == before


def test_ambiguous_players_are_left_for_review():
    data = {'a': rows(0, 2), 'b': rows(4, 6), 'c': rows(4, 6, 1)}
    assert stitch_tracks(data)[1] == 1
    assert stitch_tracks(data, require_mutual=True)[1] == 0


def test_clear_mutual_continuation_is_still_joined():
    data = {'a': rows(0, 2), 'b': rows(4, 6)}
    assert stitch_tracks(data, require_mutual=True)[1] == 1


def test_contained_fragment_cannot_remove_a_concurrent_player():
    data = {'a': rows(0, 3), 'b': rows(2, 2)}
    # Legacy endpoint checks permit discarding b inside a; conservative mode
    # remains conservative in ambiguous short overlap via bidirectional ranks.
    joined, _ = stitch_tracks(data, max_overlap=0, require_mutual=True)
    assert len(joined) == 2


def test_negative_ids_can_be_strings_or_integers():
    assert stitch_tracks({1: rows(0, 2), 2: rows(4, 6)}, different_pairs=[('1', '2')])[1] == 0


def test_component_overlap_cannot_be_hidden_by_a_short_middle_track():
    data = {'a': rows(0, 10), 'b': rows(8, 8), 'c': rows(6, 20)}
    output, _ = stitch_tracks(data, max_overlap=3, require_mutual=True)
    assert not any(any(r['frame'] == 0 for r in group) and any(r['frame'] == 20 for r in group) for group in output.values())


def test_evaluator_split_is_order_independent_and_reports_unmapped(tmp_path):
    import json
    from scripts.evaluate_stitch_constraints import run, split_pairs
    assert split_pairs([('1', '2'), ('3', '4')]) == split_pairs([('4', '3'), ('2', '1')])
    tracks = tmp_path / 'tracks.json'
    links = tmp_path / 'links.json'
    tracks.write_text(json.dumps({'tracks': {'a': rows(0, 2), 'b': rows(4, 6)}}))
    links.write_text(json.dumps({'same': [['a', 'missing']], 'different': [['a', 'b']]}))
    report = run(tracks, links)
    assert report['inputs_unchanged']
    assert report['results']['baseline']['pairs']['same']['unmapped'] == 1
    assert report['results']['baseline']['pairs']['constraint_different']['joined'] == 1
    assert report['results']['split_constraints']['pairs']['constraint_different']['joined'] == 0
