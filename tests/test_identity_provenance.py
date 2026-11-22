import json
import sys
from pathlib import Path

from app.player_identity import PlayerIdentity

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_player_cards import confirmed_card_tracks


def fixture(tmp_path):
    root = tmp_path / 'players'
    (root / 'h1').mkdir(parents=True)
    (root / 'assign').mkdir()
    (root / 'links').mkdir()
    tracks = [{'id': str(i), 'team': 'B', 'first': i * 10, 'last': i * 10 + 8, 'rows': 40, 'pictures': [], 'slot': 'MF'} for i in range(1, 4)]
    (root / 'h1/index.json').write_text(json.dumps({'tracks': tracks}))
    (root / 'assign/h1.json').write_text(json.dumps({'1': 'p1', '3': 'p1'}))
    (root / 'links/h1.json').write_text(json.dumps({'same': [['1', '2']], 'different': []}))
    (root / 'auto_notes.json').write_text(json.dumps({'notes': {'h1': {'1': {'player': 'p1'}}}}))
    (root / 'roster.json').write_text(json.dumps([{'id': 'p1', 'team': 'B', 'name': 'Test', 'number': 1, 'position': 'MF'}]))
    return PlayerIdentity(tmp_path), root


def tracks(ids):
    return {t['id']: t for t in ids.state('h1')['tracks']}


def test_legacy_reads_preserve_bytes_and_do_not_certify_automatic_links(tmp_path):
    ids, root = fixture(tmp_path)
    before = {str(p): p.read_bytes() for p in root.rglob('*.json')}
    t = tracks(ids)
    assert t['1']['assignment_evidence'] == 'auto_unconfirmed'
    assert t['2']['assignment_evidence'] == 'unverified_link'
    assert t['3']['assignment_evidence'] == 'legacy_unknown'
    assert all(x['confirmed_player'] is None for x in t.values())
    assert confirmed_card_tracks(ids.chain('h1', 'p1'), 'p1') == []
    assert before == {str(p): p.read_bytes() for p in root.rglob('*.json')}


def test_human_confirmation_is_additive_and_only_verified_links_propagate(tmp_path):
    ids, root = fixture(tmp_path)
    original = (root / 'assign/h1.json').read_bytes()
    ids.assign('h1', '1', 'p1')
    assert json.loads(original) == json.loads((root / 'assign/h1.json').read_bytes())
    t = tracks(ids)
    assert t['1']['confirmed_player'] == 'p1'
    assert t['2']['confirmed_player'] is None
    ids.link('h1', '1', '2', 'same')
    t = tracks(ids)
    assert t['2']['assignment_evidence'] == 'human_confirmed_link'
    assert {t['id'] for t in confirmed_card_tracks(ids.chain('h1', 'p1'), 'p1')} == {'1', '2'}
    ids.assign('h1', '1', '')
    assert tracks(ids)['2']['confirmed_player'] is None


def test_retracking_and_changed_assignment_invalidate_stale_provenance(tmp_path):
    ids, root = fixture(tmp_path)
    ids.assign('h1', '1', 'p1')
    index = json.loads((root / 'h1/index.json').read_text())
    index['tracks'][0]['first'] += 1
    (root / 'h1/index.json').write_text(json.dumps(index))
    assert tracks(ids)['1']['confirmed_player'] is None


def test_conflicting_group_is_never_used_in_card(tmp_path):
    ids, root = fixture(tmp_path)
    p2 = ids.set_player('', 'B', 'Second', 2, 'MF')['id']
    ids.assign('h1', '1', 'p1')
    ids.assign('h1', '2', p2)
    ids.link('h1', '1', '2', 'same')
    assert tracks(ids)['1']['confirmed_player'] is None
    assert confirmed_card_tracks(ids.chain('h1', 'p1'), 'p1') == []


def test_transitive_same_link_cannot_override_different_answer(tmp_path):
    ids, root = fixture(tmp_path)
    ids.assign('h1', '1', 'p1')
    ids.link('h1', '1', '2', 'same')
    ids.link('h1', '2', '3', 'same')
    ids.link('h1', '1', '3', 'different')
    assert all(t['conflict'] for t in tracks(ids).values())
    assert confirmed_card_tracks(ids.chain('h1', 'p1'), 'p1') == []
