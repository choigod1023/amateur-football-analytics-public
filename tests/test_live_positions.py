import json

from app.live_feedback import LiveAnalyzer
from app.live_positions import PositionLog, read_positions
from app.report_scenes import second_metrics
from app.team_tactics import seconds_series


def squad(x_front, shift=0.0):
    xs = [x_front - 4 * i for i in range(10)]
    return [(i + 1, x + shift, ((i * 11) % 40) - 20) for i, x in enumerate(xs)] + [(11, -42.0, 0.0)]


def test_one_line_per_whole_second_and_a_header_first(tmp_path):
    log = PositionLog(tmp_path / 'p.jsonl', 'B', 'A', -1, 89.0, 62.0, 64.0)
    written = [log.add(64 + k * 0.2, [(1, 1.0, 2.0)], [(9, -1.0, 0.5)]) for k in range(15)]
    log.close()
    lines = [json.loads(l) for l in (tmp_path / 'p.jsonl').read_text(encoding='utf-8').splitlines()]
    assert sum(written) == 3 and lines[0]['type'] == 'header' and lines[0]['direction'] == -1 and lines[0]['first_second'] == 64.0
    assert [l['type'] for l in lines[1:]] == ['second'] * 3 and lines[1]['team'] == [[1, 1.0, 2.0]]


def test_the_file_reads_back_as_one_frame_per_second_in_the_form_of_metre_rows(tmp_path):
    log = PositionLog(tmp_path / 'p.jsonl', 'B', 'A', 1, 89.0, 62.0)
    for k in range(10):
        log.add(float(k), [(1, 10.0 + k, 3.0), (2, 5.0, -4.0)], [(9, -10.0, 0.0)])
    log.close()
    header, by_frame, frames = read_positions(tmp_path / 'p.jsonl')
    assert frames == 10 and header['team'] == 'B' and sorted(by_frame) == list(range(10))
    assert by_frame[3]['B'] == [(1, 13.0, 3.0), (2, 5.0, -4.0)] and by_frame[3]['A'] == [(9, -10.0, 0.0)]
    assert all(isinstance(row, tuple) and len(row) == 3 for team in by_frame[0].values() for row in team)


def test_a_broken_line_is_skipped_and_a_file_without_header_is_refused(tmp_path):
    path = tmp_path / 'p.jsonl'
    path.write_text('{"type": "header", "team": "B", "other": "A", "direction": 1}\nnot json\n{"type": "second", "time": 5.0, "team": [[1, 0, 0]], "other": []}\n', encoding='utf-8')
    header, by_frame, frames = read_positions(path)
    assert frames == 1 and by_frame[0]['B'] == [(1, 0, 0)]
    path.write_text('{"type": "second", "time": 5.0, "team": [], "other": []}\n', encoding='utf-8')
    try:
        read_positions(path)
    except ValueError:
        return
    raise AssertionError('a file without a header must be refused')


def test_the_positions_of_a_run_feed_the_half_time_summary_readers(tmp_path):
    """positions.jsonl -> by_frame -> the same functions that sum up a half from stored tracks (team shape per second and second_metrics)."""
    analyzer = LiveAnalyzer(direction=1, fps=5.0)
    log = PositionLog(tmp_path / 'p.jsonl', 'B', 'A', 1, 89.0, 62.0)
    for step in range(int(20 * analyzer.fps)):
        t = step / analyzer.fps
        team, other = squad(30.0), [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(30.0))]
        analyzer.update(t, team, other)
        log.add(t, analyzer.held('team', analyzer.last_sample), analyzer.held('other', analyzer.last_sample))
    log.close()
    header, by_frame, frames = read_positions(tmp_path / 'p.jsonl')
    series = seconds_series(by_frame, 'B', 'A', header['direction'], 1.0, frames)
    assert len(series) == frames == 20 and any(row['ours'] for row in series.values())
    metrics = second_metrics(by_frame[5]['B'], by_frame[5]['A'], header['direction'], 6)
    assert metrics and 'opponent_back_line' in metrics


def test_the_report_script_reads_the_positions_with_its_own_series_function(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from build_team_report import series_of
    log = PositionLog(tmp_path / 'p.jsonl', 'B', 'A', 1, 89.0, 62.0)
    for k in range(12):
        log.add(float(k), squad(30.0), [(100 + i, -x, y) for i, (_t, x, y) in enumerate(squad(30.0))])
    log.close()
    header, by_frame, frames = read_positions(tmp_path / 'p.jsonl')
    series = series_of(by_frame, 'B', 'A', header['direction'], 1, frames, 6)
    assert sorted(series) == list(range(12))
