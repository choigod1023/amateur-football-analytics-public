import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from migrate_player_answers import migrate_assign, migrate_links, successors  # noqa: E402


def rows(frames, x):
    return [{'frame': f, 'team': 'B', 'box': [x, 100, x + 30, 180]} for f in frames]


def test_a_joined_piece_follows_the_track_it_was_joined_into():
    old = {'1': rows(range(0, 10), 100), '2': rows(range(10, 20), 100), '3': rows(range(0, 20), 500)}
    new = {'1': rows(range(0, 20), 100), '3': rows(range(0, 20), 500)}
    where = successors(old, new, ['1', '2', '3', '9'])
    assert where == {'1': '1', '2': '1', '3': '3', '9': None}


def test_answers_links_and_conflicts_follow_the_mapping():
    where = {'1': '1', '2': '1', '3': '3', '4': None}
    assign, conflicts, lost = migrate_assign({'1': 'p1', '2': 'p2', '3': 'p3', '4': 'p4'}, where, {'1': 50, '2': 10, '3': 40, '4': 5})
    assert assign == {'1': 'p1', '3': 'p3'} and conflicts == [('2', 'p2', 'p1')] and lost == ['4']
    links, dropped, merged = migrate_links({'same': [['1', '2'], ['1', '3']], 'different': [['1', '2'], ['2', '3']]}, where)
    assert links == {'same': [['1', '3']], 'different': [['1', '3']]} and dropped == [('1', '2')] and merged == [('1', '2')]
