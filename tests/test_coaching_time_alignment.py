from app.live_feedback import LiveAnalyzer
from scripts.prepare_difference_scenes import unmatched


def test_closed_second_uses_its_own_players_not_future_frame():
    analyzer = LiveAnalyzer(1, minimum_players=1)
    captured = []
    analyzer._close_second = lambda second, team, other: captured.append((second, team, other))
    analyzer._check = lambda *a: []
    analyzer.update(0, [(1, 0, 0)], [])
    analyzer.update(.8, [(1, 2, 0)], [])
    analyzer.update(1, [(1, 50, 0)], [])
    assert captured == [(0, [(1, 2, 0)], [])]
    analyzer.update(3, [], [])
    assert captured[-1] == (1, [(1, 50, 0)], [])


def test_matching_alerts_is_one_to_one_and_kind_specific():
    before = [{'time': 10, 'kind': 'run'}, {'time': 11, 'kind': 'run'}, {'time': 20, 'kind': 'line_drop'}]
    after = [{'time': 12, 'kind': 'run'}, {'time': 20, 'kind': 'run'}]
    removed, added = unmatched(before, after)
    assert removed == before[1:]
    assert added == after[1:]
