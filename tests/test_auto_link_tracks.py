import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from auto_link_tracks import auto_pairs  # noqa: E402


def track(ident, team, first, last, a, b, slot=None):
    return {'id': ident, 'team': team, 'first': first, 'last': last, 'first_pos': list(a), 'last_pos': list(b), 'slot': slot}


def test_a_clear_continuation_is_joined():
    tracks = [track('1', 'B', 0, 20, (0, 0), (10, 0)), track('2', 'B', 21, 40, (10.5, 0.5), (20, 0))]
    assert list(auto_pairs(tracks)) == [('1', '2')]


def test_two_possible_successors_or_a_jump_or_another_team_or_a_no_answer_join_nothing():
    two = [track('1', 'B', 0, 20, (0, 0), (10, 0)), track('2', 'B', 21, 40, (10.5, 0.5), (20, 0)), track('3', 'B', 21, 40, (10.6, 0.4), (20, 5))]
    assert auto_pairs(two) == {}                                                              # no doubt-free choice between 2 and 3
    far = [track('1', 'B', 0, 20, (0, 0), (10, 0)), track('2', 'B', 21, 40, (30, 0), (35, 0))]
    assert auto_pairs(far) == {}
    other = [track('1', 'B', 0, 20, (0, 0), (10, 0)), track('2', 'A', 21, 40, (10.5, 0), (20, 0))]
    assert auto_pairs(other) == {}
    plain = [track('1', 'B', 0, 20, (0, 0), (10, 0)), track('2', 'B', 21, 40, (10.5, 0.5), (20, 0))]
    assert auto_pairs(plain, different=[('2', '1')]) == {}
    lines = [track('1', 'B', 0, 20, (0, 0), (10, 0), 'LCB'), track('2', 'B', 21, 40, (10.5, 0.5), (20, 0), 'ST')]
    assert auto_pairs(lines) == {}
    overlap = [track('1', 'B', 0, 20, (0, 0), (10, 0)), track('2', 'B', 19, 40, (10.5, 0.5), (20, 0))]
    assert auto_pairs(overlap) == {}
